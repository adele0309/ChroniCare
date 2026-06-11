from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from alertes_notifications.services import create_alert, create_notification


def _premier_jour_du_mois(date=None):
    d = date or timezone.now().date()
    return d.replace(day=1)


def check_stock_disponible(prescription):
    """Vérifie que chaque item de la prescription a un stock suffisant.

    Retourne une liste de dicts {'medication', 'requis', 'disponible'} pour les ruptures.
    """
    ruptures = []
    for item in prescription.items.select_related('medication').all():
        dispo = item.medication.stock_total
        if dispo < item.quantite:
            ruptures.append({
                'medication': item.medication.nom,
                'requis':     item.quantite,
                'disponible': dispo,
            })
    return ruptures


@transaction.atomic
def deliver_prescription_service(prescription, user, periode=None):
    """Dispense une prescription pour la période donnée.

    Retourne (dispensation, None) en cas de succès,
    ou (None, message_erreur) en cas d'échec.

    Logique :
    - Bloque si la prescription est annulée.
    - Bloque si une dispensation existe déjà pour cette période.
    - Bloque si le stock est insuffisant pour un médicament.
    - Sélectionne les lots en FIFO (date d'expiration la plus proche en premier).
    - Décrémente le stock lot par lot.
    - Enregistre chaque mouvement dans MouvementStock.
    - Met à jour le statut et le prochain renouvellement.
    - Notifie le médecin prescripteur.
    """
    from .models import Dispensation, DispensationItem, MouvementStock, MedicationLot

    if prescription.statut == 'annulee':
        return None, "La prescription est annulée."

    periode = periode or _premier_jour_du_mois()

    # Double dispensation pour la même période
    if Dispensation.objects.filter(prescription=prescription, periode=periode).exists():
        return None, "Ce traitement a déjà été dispensé pour cette période."

    # Vérification globale du stock avant toute opération
    ruptures = check_stock_disponible(prescription)
    if ruptures:
        details = ", ".join(
            f"{r['medication']} (requis : {r['requis']}, disponible : {r['disponible']})"
            for r in ruptures
        )
        return None, f"Stock insuffisant — {details}."

    # Création de la dispensation
    dispensation = Dispensation.objects.create(
        prescription=prescription,
        pharmacien=user,
        periode=periode,
    )

    # Dispensation item par item avec sélection FIFO
    for item in prescription.items.select_related('medication').all():
        quantite_restante = item.quantite

        lots_fifo = MedicationLot.objects.filter(
            medication=item.medication,
            quantite__gt=0,
            date_expiration__gt=timezone.now().date(),
        ).order_by('date_expiration')  # lot expirant le plus tôt en premier

        for lot in lots_fifo:
            if quantite_restante <= 0:
                break

            prendre = min(lot.quantite, quantite_restante)

            DispensationItem.objects.create(
                dispensation=dispensation,
                medication=item.medication,
                lot=lot,
                quantite=prendre,
            )

            # Décrémentation du stock
            lot.quantite -= prendre
            lot.save(update_fields=['quantite'])

            # Audit mouvement
            MouvementStock.objects.create(
                lot=lot,
                type_mouvement='dispensation',
                quantite=-prendre,
                utilisateur=user,
                dispensation=dispensation,
                reference=(
                    f"Prescription #{prescription.id} — "
                    f"{prescription.patient.nom} {prescription.patient.prenom}"
                ),
            )

            quantite_restante -= prendre

    # Mise à jour statut et prochain renouvellement
    prescription.statut = 'active'
    prescription.date_prochain_renouvellement = (
        timezone.now().date() + timedelta(days=prescription.duree_standard)
    )
    prescription.save(update_fields=['statut', 'date_prochain_renouvellement'])

    # Notification au médecin prescripteur
    _notifier_medecin_dispensation(prescription, dispensation)

    # Alerte si stock critique après dispensation
    _verifier_alertes_stock_post_dispensation(dispensation)

    return dispensation, None


def _notifier_medecin_dispensation(prescription, dispensation):
    """Notifie le médecin que les médicaments ont été remis au patient."""
    medecin = prescription.medecin
    if not medecin:
        return
    mois = dispensation.periode.strftime('%B %Y') if dispensation.periode else '—'
    create_notification(
        medecin,
        f"Traitement dispensé — {prescription.patient.nom}",
        (
            f"Le traitement de {prescription.patient.nom} {prescription.patient.prenom} "
            f"a été dispensé par la pharmacie pour la période {mois}."
        ),
        'info',
    )


def _verifier_alertes_stock_post_dispensation(dispensation):
    """Génère des alertes si un médicament dispensé passe sous le seuil d'alerte."""
    patient = dispensation.prescription.patient
    for item in dispensation.items.select_related('medication').all():
        med = item.medication
        if med.est_en_rupture:
            create_alert(
                patient,
                f"Stock critique : {med.nom} ({med.stock_total} unités restantes)",
                alert_type='warning',
                source='stock_pharmacie',
            )
            # Notification aux pharmaciens actifs
            from django.contrib.auth import get_user_model
            User = get_user_model()
            for pharmacien in User.objects.filter(role='pharmacist', is_active=True):
                create_notification(
                    pharmacien,
                    f"Rupture de stock — {med.nom}",
                    (
                        f"Le stock de {med.nom} est passé sous le seuil d'alerte "
                        f"({med.stock_total} unités). Un réapprovisionnement est nécessaire."
                    ),
                    'urgent',
                )


def notifier_renouvellements_imminents():
    """À appeler périodiquement (ex: tâche Celery quotidienne).

    Notifie le médecin et le patient pour chaque prescription dont le
    renouvellement est dans les 7 prochains jours et n'a pas encore été dispensé
    pour la période en cours.
    """
    from .models import Prescription, Dispensation
    aujourd_hui = timezone.now().date()
    dans_7_jours = aujourd_hui + timedelta(days=7)

    prescriptions = Prescription.objects.filter(
        statut__in=['en_attente', 'active'],
        date_prochain_renouvellement__lte=dans_7_jours,
    ).select_related('patient', 'medecin', 'patient__compte_patient')

    for prescription in prescriptions:
        periode = _premier_jour_du_mois(prescription.date_prochain_renouvellement)
        if Dispensation.objects.filter(prescription=prescription, periode=periode).exists():
            continue  # déjà dispensé pour ce mois

        patient_user = getattr(prescription.patient, 'compte_patient', None)
        mois = prescription.date_prochain_renouvellement.strftime('%d/%m/%Y')

        if patient_user:
            create_notification(
                patient_user,
                "Renouvellement de traitement",
                f"Votre traitement est à renouveler avant le {mois}. "
                "Présentez-vous à la pharmacie.",
                'info',
            )
        if prescription.medecin:
            create_notification(
                prescription.medecin,
                f"Renouvellement — {prescription.patient.nom}",
                f"La prescription de {prescription.patient.nom} doit être renouvelée avant le {mois}.",
                'info',
            )

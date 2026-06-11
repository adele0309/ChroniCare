from django.core.exceptions import ValidationError
from alertes_notifications.services import create_alert, create_notification
from .models import SuiviMedical


def validate_suivi_type(suivi):
    if suivi.type_suivi == 'rdv' and not suivi.appointment:
        raise ValidationError("Un suivi avec RDV doit avoir un rendez-vous.")
    if suivi.type_suivi == 'direct' and suivi.appointment:
        raise ValidationError("Un suivi direct ne doit pas avoir de rendez-vous.")


def check_alerts_suivi(suivi):
    patient = suivi.patient
    user    = getattr(patient, "compte_patient", None)

    def _alerte(message, alert_type, source, notif_title, notif_msg, notif_type):
        create_alert(patient, message, alert_type=alert_type, source=source)
        if user:
            create_notification(user, notif_title, notif_msg, notif_type)

    # ── Glycémie ─────────────────────────────────────────────────────────────
    if suivi.glycemie:
        if suivi.glycemie > 2.0:
            _alerte("Glycémie critique", "critical", "glycemia",
                    "Alerte critique glycémie", "Votre glycémie est à un niveau critique.", "urgent")
        elif suivi.glycemie > 1.26:
            _alerte("Glycémie élevée détectée", "critical", "glycemia",
                    "Alerte glycémie", "Votre glycémie est élevée. Consultez un médecin.", "urgent")

    # ── Tension artérielle ───────────────────────────────────────────────────
    if suivi.tension_systolique:
        if suivi.tension_systolique > 18:
            _alerte("Hypertension critique", "critical", "blood_pressure",
                    "Alerte critique tension", "Votre tension est à un niveau critique.", "urgent")
        elif suivi.tension_systolique > 14:
            _alerte("Hypertension détectée", "warning", "blood_pressure",
                    "Alerte tension", "Votre tension est élevée.", "warning")

    # ── CD4 ──────────────────────────────────────────────────────────────────
    if suivi.cd4:
        if suivi.cd4 < 100:
            _alerte("Immunité critique (CD4 < 100)", "critical", "cd4",
                    "Alerte critique CD4", "Votre taux de CD4 est à un niveau critique.", "urgent")
        elif suivi.cd4 < 200:
            _alerte("Immunité très basse (CD4)", "critical", "cd4",
                    "Alerte immunitaire", "Votre taux de CD4 est bas.", "urgent")

    # ── Charge virale ────────────────────────────────────────────────────────
    if suivi.charge_virale:
        if suivi.charge_virale > 100_000:
            _alerte("Charge virale critique", "critical", "viral_load",
                    "Alerte critique charge virale", "Votre charge virale est à un niveau critique.", "urgent")
        elif suivi.charge_virale > 1000:
            _alerte("Charge virale élevée", "warning", "viral_load",
                    "Alerte charge virale", "Votre charge virale est élevée.", "urgent")

    # ── Hémoglobine ──────────────────────────────────────────────────────────
    if suivi.hemoglobine is not None:
        if suivi.hemoglobine < 7.0:
            _alerte("Anémie sévère (hémoglobine critique)", "critical", "hemoglobine",
                    "Alerte critique hémoglobine", "Votre hémoglobine est à un niveau critique.", "urgent")
        elif suivi.hemoglobine < 12.0:
            _alerte("Anémie détectée", "warning", "hemoglobine",
                    "Alerte hémoglobine", "Votre taux d'hémoglobine est bas.", "warning")

    # ── Cholestérol ──────────────────────────────────────────────────────────
    if suivi.cholesterol is not None:
        if suivi.cholesterol > 3.0:
            _alerte("Cholestérol critique", "critical", "cholesterol",
                    "Alerte critique cholestérol", "Votre cholestérol est à un niveau critique.", "urgent")
        elif suivi.cholesterol > 2.0:
            _alerte("Cholestérol élevé", "warning", "cholesterol",
                    "Alerte cholestérol", "Votre cholestérol est élevé.", "warning")

    # ── Créatinine ───────────────────────────────────────────────────────────
    if suivi.creatinine is not None:
        if suivi.creatinine > 20.0:
            _alerte("Insuffisance rénale critique (créatinine)", "critical", "creatinine",
                    "Alerte critique créatinine", "Votre créatinine est à un niveau critique.", "urgent")
        elif suivi.creatinine > 12.0:
            _alerte("Créatinine élevée", "warning", "creatinine",
                    "Alerte rénale", "Votre créatinine est élevée.", "warning")

    # ── Urée ─────────────────────────────────────────────────────────────────
    if suivi.uree is not None:
        if suivi.uree > 0.60:
            _alerte("Urée critique (insuffisance rénale)", "critical", "uree",
                    "Alerte critique urée", "Votre taux d'urée est à un niveau critique.", "urgent")
        elif suivi.uree > 0.45:
            _alerte("Urée élevée", "warning", "uree",
                    "Alerte urée", "Votre taux d'urée est élevé.", "warning")

    # ── Transaminases ────────────────────────────────────────────────────────
    if suivi.transaminases is not None:
        if suivi.transaminases > 200:
            _alerte("Transaminases critiques (insuffisance hépatique)", "critical", "transaminases",
                    "Alerte critique transaminases", "Vos transaminases sont à un niveau critique.", "urgent")
        elif suivi.transaminases > 40:
            _alerte("Transaminases élevées", "warning", "transaminases",
                    "Alerte hépatique", "Vos transaminases sont élevées.", "warning")


def create_suivi_from_rdv(rdv, data):
    suivi = SuiviMedical.objects.create(
        appointment=rdv,
        patient=rdv.patient,
        medecin=rdv.doctor,
        **data,
    )
    check_alerts_suivi(suivi)
    return suivi

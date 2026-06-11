"""
Commande : python manage.py seed_data
Insère des données de démonstration complètes dans ChroniCare.
"""
import random
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = "Peuple la base de données avec des données de démonstration réalistes."

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Supprime toutes les données existantes avant l\'insertion.',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self._flush()

        self.stdout.write(self.style.WARNING("=== Insertion des données de démonstration ==="))

        users       = self._create_users()
        maladies    = self._create_maladies()
        medications = self._create_medications()
        patients    = self._create_patients(users, maladies)
        self._create_appointments(patients, users)
        suivis      = self._create_suivis(patients, users)
        self._create_prescriptions(patients, users, suivis, medications, maladies)
        self._create_lab_tests(patients, users, suivis, maladies)
        self._create_alerts_notifications(patients, users)

        self.stdout.write(self.style.SUCCESS("\nOK Données insérées avec succès !"))
        self.stdout.write("")
        self.stdout.write("  Comptes crees (mot de passe : Pass1234!) :")
        self.stdout.write("  medecins    : amadou12 / sekou01 / moussa01")
        self.stdout.write("  infirmiers  : mariama01 / ibrahima01")
        self.stdout.write("  pharmacien  : mamadou01")
        self.stdout.write("  labo        : mohamed01")
        self.stdout.write("  patients    : mamadou02 / fatoumata01 / ibrahima02 / mariama02")
        self.stdout.write("               oumar01 / aminata01 / aboubacar01 / kadiatou01")

    # ──────────────────────────────────────────────────────────────────
    # FLUSH
    # ──────────────────────────────────────────────────────────────────
    def _flush(self):
        from alertes_notifications.models import Alert, Notification
        from laboratoire.models import LabTest
        from pharmacie.models import (
            Dispensation, DispensationItem, MouvementStock,
            Prescription, PrescriptionItem, MedicationLot, Medication,
        )
        from suivi_medical.models import SuiviMedical
        from appointments.models import Appointment
        from maladies.models import PatientMaladie, Maladie, SeuilAlerte
        from patients.models import Patient

        self.stdout.write("  Suppression des données existantes…")
        for model in [
            Notification, Alert,
            LabTest,
            MouvementStock, DispensationItem, Dispensation,
            PrescriptionItem, Prescription,
            SuiviMedical,
            Appointment,
            SeuilAlerte, PatientMaladie,
            Patient,
            MedicationLot, Medication,
            Maladie,
        ]:
            model.objects.all().delete()
        # Supprimer uniquement les comptes créés par le seed (format avec point)
        # Les comptes originaux (adele09, amadou12, etc.) sont préservés.
        User.objects.filter(username__contains='.').delete()
        self.stdout.write(self.style.WARNING("  Données supprimées."))

    # ──────────────────────────────────────────────────────────────────
    # USERS
    # ──────────────────────────────────────────────────────────────────
    def _create_users(self):
        self.stdout.write("  Creation des utilisateurs…")
        PASSWORD = "Pass1234!"

        def make(username, first, last, role, specialite=None, **kw):
            u, created = User.objects.get_or_create(
                username=username,
                defaults=dict(
                    first_name=first, last_name=last,
                    email=f"{username}@chronicare.sn",
                    role=role, specialite=specialite,
                    is_active=True, is_active_status=True,
                    **kw,
                ),
            )
            if created:
                u.set_password(PASSWORD)
                u.save()
            return u

        # Récupérer l'admin existant (adele09)
        admin = User.objects.filter(is_superuser=True).order_by('id').first()

        # Dr. amadou12 existe déjà — on le réutilise directement
        dr1 = User.objects.get(username="amadou12")
        if not dr1.specialite:
            dr1.specialite = "Cardiologie"
            dr1.save(update_fields=["specialite"])

        # 2 nouveaux médecins au format prenom+chiffre
        dr2 = make("sekou01",    "Sekou",     "Diallo",  "doctor", specialite="Medecine interne")
        dr3 = make("moussa01",   "Moussa",    "Kone",    "doctor", specialite="Endocrinologie")

        inf1   = make("mariama01",   "Mariama",    "Balde",   "nurse")
        inf2   = make("ibrahima01",  "Ibrahima",   "Conde",   "nurse")
        pharma = make("mamadou01",   "Mamadou",    "Sow",     "pharmacist")
        labo   = make("mohamed01",   "Mohamed",    "Keita",   "lab")

        # Comptes patients au format prenom+chiffre
        p_accounts = []
        patient_data = [
            ("mamadou02",   "Mamadou",   "Kouyate"),
            ("fatoumata01", "Fatoumata", "Bah"),
            ("ibrahima02",  "Ibrahima",  "Diallo"),
            ("mariama02",   "Mariama",   "Camara"),
            ("oumar01",     "Oumar",     "Keita"),
            ("aminata01",   "Aminata",   "Toure"),
            ("aboubacar01", "Aboubacar", "Sylla"),
            ("kadiatou01",  "Kadiatou",  "Barry"),
        ]
        for uname, fn, ln in patient_data:
            p_accounts.append(make(uname, fn, ln, "patient"))

        created_count = User.objects.count()
        self.stdout.write(self.style.SUCCESS(f"    OK {created_count} utilisateurs"))
        return {
            "admin":            admin,
            "doctors":          [dr1, dr2, dr3],
            "nurses":           [inf1, inf2],
            "pharma":           pharma,
            "labo":             labo,
            "patient_accounts": p_accounts,
        }

    # ──────────────────────────────────────────────────────────────────
    # MALADIES
    # ──────────────────────────────────────────────────────────────────
    def _create_maladies(self):
        from maladies.models import Maladie
        self.stdout.write("  Création des maladies…")

        data = [
            ("Diabète de type 2",            "metabolique",
             "Maladie chronique caractérisée par une hyperglycémie due à une résistance à l'insuline."),
            ("Hypertension artérielle",       "cardiovasculaire",
             "Pression artérielle systolique ≥ 140 mmHg ou diastolique ≥ 90 mmHg de façon persistante."),
            ("VIH / SIDA",                   "infectieuse",
             "Infection par le virus de l'immunodéficience humaine affectant le système immunitaire."),
            ("Insuffisance rénale chronique", "rénale",
             "Dégradation progressive et irréversible de la fonction rénale sur plus de 3 mois."),
            ("Asthme bronchique",             "respiratoire",
             "Maladie inflammatoire chronique des voies respiratoires avec obstruction réversible."),
            ("Hépatite B chronique",          "infectieuse",
             "Infection chronique par le virus de l'hépatite B pouvant évoluer vers la cirrhose."),
            ("Dyslipidémie",                 "metabolique",
             "Anomalie du taux de lipides sanguins (cholestérol LDL élevé, HDL bas, triglycérides élevés)."),
            ("Anémie chronique",              "autre",
             "Taux d'hémoglobine inférieur à la normale de façon persistante."),
        ]

        maladies = {}
        for nom, typ, desc in data:
            m, _ = Maladie.objects.get_or_create(nom=nom, defaults={"type": typ, "description": desc})
            maladies[nom] = m

        self.stdout.write(self.style.SUCCESS(f"    OK {len(maladies)} maladies"))
        return maladies

    # ──────────────────────────────────────────────────────────────────
    # MEDICATIONS
    # ──────────────────────────────────────────────────────────────────
    def _create_medications(self):
        from pharmacie.models import Medication, MedicationLot, MouvementStock
        self.stdout.write("  Création des médicaments et stocks…")

        meds_data = [
            ("Metformine 500mg",   "comprime",  10, 500),
            ("Amlodipine 5mg",     "comprime",  10, 750),
            ("Furosémide 40mg",    "comprime",  8,  300),
            ("Lisinopril 10mg",    "comprime",  10, 600),
            ("Efavirenz 600mg",    "comprime",  15, 1200),
            ("Lamivudine 150mg",   "comprime",  15, 900),
            ("Ténofovir 300mg",    "comprime",  15, 1100),
            ("Salbutamol inhalé",  "autre",     5,  2500),
            ("Prednisolone 5mg",   "comprime",  8,  400),
            ("Atorvastatine 20mg", "comprime",  10, 700),
            ("Fumarate ferreux",   "comprime",  10, 250),
            ("Entécavir 0,5mg",    "comprime",  12, 3500),
        ]

        meds = {}
        for nom, unite, stock_min, prix in meds_data:
            med, _ = Medication.objects.get_or_create(
                nom=nom,
                defaults={"unite": unite, "stock_minimum": stock_min, "prix": prix},
            )
            meds[nom] = med

            # Créer un lot de stock si pas encore de lot
            if not med.lots.exists():
                lot = MedicationLot.objects.create(
                    medication=med,
                    numero_lot=f"LOT-{med.id:04d}A",
                    quantite=random.randint(80, 200),
                    date_expiration=date.today() + timedelta(days=random.randint(180, 730)),
                    date_reception=date.today() - timedelta(days=random.randint(10, 90)),
                )
                # Mouvement d'entrée initial
                MouvementStock.objects.create(
                    lot=lot,
                    type_mouvement='reception',
                    quantite=lot.quantite,
                    reference=f"Réception initiale {lot.numero_lot}",
                )

        # Médicament en rupture volontaire pour tester les alertes
        med_rupture = meds.get("Fumarate ferreux")
        if med_rupture and med_rupture.lots.exists():
            lot = med_rupture.lots.first()
            lot.quantite = 3  # sous le seuil de 10
            lot.save()

        self.stdout.write(self.style.SUCCESS(f"    OK {len(meds)} médicaments"))
        return meds

    # ──────────────────────────────────────────────────────────────────
    # PATIENTS
    # ──────────────────────────────────────────────────────────────────
    def _create_patients(self, users, maladies):
        from patients.models import Patient
        from maladies.models import PatientMaladie
        self.stdout.write("  Création des patients…")

        doctors = users["doctors"]
        dr1, dr2, dr3 = doctors

        # (nom, prenom, ddn, sexe, tel, groupe, urgence, adresse, assurance,
        #  medecin_traitant, ant_perso, ant_familiaux, maladies_actives)
        patients_data = [
            {
                "nom": "Kouyaté", "prenom": "Mamadou",
                "ddn": date(1979, 3, 15), "sexe": "M",
                "tel": "+224622100001", "groupe": "B+",
                "urgence": "+224622200001", "adresse": "Conakry, Ratoma",
                "assurance": "CNSS Guinée", "medecin": dr1,
                "ant_perso": "Tabagisme sevré 2018. Obésité abdominale.",
                "ant_fam": "Père diabétique, mère hypertendue.",
                "maladies": [
                    (maladies["Diabète de type 2"],            "active", date(2017, 6, 10)),
                    (maladies["Hypertension artérielle"],      "stable", date(2019, 2, 20)),
                ],
            },
            {
                "nom": "Bah", "prenom": "Fatoumata",
                "ddn": date(1986, 7, 22), "sexe": "F",
                "tel": "+224622100002", "groupe": "O+",
                "urgence": "+224622200002", "adresse": "Conakry, Dixinn",
                "assurance": None, "medecin": dr2,
                "ant_perso": "Découverte VIH 2015. Traitement ARV depuis 2015.",
                "ant_fam": "Aucun antécédent familial notable.",
                "maladies": [
                    (maladies["VIH / SIDA"],    "stable", date(2015, 4, 5)),
                    (maladies["Anémie chronique"], "active", date(2018, 9, 12)),
                ],
            },
            {
                "nom": "Diallo", "prenom": "Ibrahima",
                "ddn": date(1972, 11, 8), "sexe": "M",
                "tel": "+224622100003", "groupe": "A+",
                "urgence": "+224622200003", "adresse": "Conakry, Kaloum",
                "assurance": "Mutuelle Fonctionnaires", "medecin": dr2,
                "ant_perso": "Néphropathie diabétique. Dialyse envisagée.",
                "ant_fam": "Frère insuffisant rénal.",
                "maladies": [
                    (maladies["Hypertension artérielle"],       "active", date(2014, 1, 15)),
                    (maladies["Insuffisance rénale chronique"], "active", date(2020, 8, 3)),
                ],
            },
            {
                "nom": "Camara", "prenom": "Mariama",
                "ddn": date(1995, 5, 30), "sexe": "F",
                "tel": "+224622100004", "groupe": "AB+",
                "urgence": "+224622200004", "adresse": "Conakry, Matoto",
                "assurance": None, "medecin": dr1,
                "ant_perso": "Asthme depuis l'enfance. Hospitalisée 2x pour crise sévère.",
                "ant_fam": "Mère asthmatique.",
                "maladies": [
                    (maladies["Asthme bronchique"], "active", date(2008, 3, 20)),
                ],
            },
            {
                "nom": "Keïta", "prenom": "Oumar",
                "ddn": date(1963, 9, 4), "sexe": "M",
                "tel": "+224622100005", "groupe": "A-",
                "urgence": "+224622200005", "adresse": "Conakry, Ratoma",
                "assurance": "CNSS Guinée", "medecin": dr3,
                "ant_perso": "Diabète diagnostiqué à 50 ans. Dyslipidémie.",
                "ant_fam": "Père décédé d'un AVC.",
                "maladies": [
                    (maladies["Diabète de type 2"], "active", date(2013, 7, 18)),
                    (maladies["Dyslipidémie"],      "stable", date(2015, 11, 5)),
                ],
            },
            {
                "nom": "Touré", "prenom": "Aminata",
                "ddn": date(1991, 12, 17), "sexe": "F",
                "tel": "+224622100006", "groupe": "O-",
                "urgence": "+224622200006", "adresse": "Conakry, Matam",
                "assurance": None, "medecin": dr2,
                "ant_perso": "Hépatite B découverte en 2019 lors d'un bilan prénatal.",
                "ant_fam": "Père porteur VHB.",
                "maladies": [
                    (maladies["Hépatite B chronique"], "active", date(2019, 5, 22)),
                ],
            },
            {
                "nom": "Sylla", "prenom": "Aboubacar",
                "ddn": date(1977, 2, 28), "sexe": "M",
                "tel": "+224622100007", "groupe": "B-",
                "urgence": "+224622200007", "adresse": "Conakry, Kaloum",
                "assurance": "Mutuelle Fonctionnaires", "medecin": dr1,
                "ant_perso": "HTA mal contrôlée. Non-observant au traitement.",
                "ant_fam": "Mère hypertendue, grand-père AVC.",
                "maladies": [
                    (maladies["Hypertension artérielle"], "active", date(2016, 3, 10)),
                ],
            },
            {
                "nom": "Barry", "prenom": "Kadiatou",
                "ddn": date(1969, 8, 11), "sexe": "F",
                "tel": "+224622100008", "groupe": "AB-",
                "urgence": "+224622200008", "adresse": "Conakry, Dixinn",
                "assurance": "CNSS Guinée", "medecin": dr3,
                "ant_perso": "Diabète et HTA diagnostiqués simultanément en 2018.",
                "ant_fam": "Sœur diabétique, père hypertensif.",
                "maladies": [
                    (maladies["Diabète de type 2"],       "active", date(2018, 4, 15)),
                    (maladies["Hypertension artérielle"], "active", date(2018, 4, 15)),
                ],
            },
        ]

        patient_accounts = users["patient_accounts"]
        patients = []
        admin = users["admin"]

        for i, d in enumerate(patients_data):
            p, _ = Patient.objects.get_or_create(
                nom=d["nom"], prenom=d["prenom"],
                defaults={
                    "date_naissance":         d["ddn"],
                    "sexe":                   d["sexe"],
                    "telephone":              d["tel"],
                    "groupe_sanguin":         d["groupe"],
                    "contact_urgence":        d["urgence"],
                    "adresse":                d["adresse"],
                    "assurance":              d["assurance"],
                    "medecin_traitant":       d["medecin"],
                    "antecedents_personnels": d["ant_perso"],
                    "antecedents_familiaux":  d["ant_fam"],
                    "cree_par":               admin,
                    "compte_patient":         patient_accounts[i],
                },
            )
            patients.append(p)

            # Lier les maladies
            for maladie, status, date_diag in d["maladies"]:
                PatientMaladie.objects.get_or_create(
                    patient=p, maladie=maladie,
                    defaults={"status": status, "date_diagnostic": date_diag},
                )

        self.stdout.write(self.style.SUCCESS(f"    OK {len(patients)} patients"))
        return patients

    # ──────────────────────────────────────────────────────────────────
    # APPOINTMENTS
    # ──────────────────────────────────────────────────────────────────
    def _create_appointments(self, patients, users):
        from appointments.models import Appointment
        self.stdout.write("  Création des rendez-vous…")

        dr1, dr2, dr3 = users["doctors"]
        admin = users["admin"]
        today = date.today()

        # Chaque rendez-vous passé est créé avec bulk_create pour
        # contourner la validation "date dans le passé" du modèle.
        rdvs_passes = []
        rdvs_futurs = []

        # Données : (patient_idx, doctor, delta_jours, heure, motif, status)
        schedule = [
            # Passés (effectués)
            (0, dr1, -90, time(8, 0),  "Suivi diabète + HTA",                "effectue"),
            (0, dr2, -60, time(9, 0),  "Consultation cardiologie",            "effectue"),
            (1, dr2, -75, time(10, 0), "Suivi VIH – CD4 et charge virale",    "effectue"),
            (1, dr1, -45, time(11, 0), "Bilan anémie",                        "effectue"),
            (2, dr2, -80, time(8, 30), "Suivi IRC + HTA",                     "effectue"),
            (2, dr3, -50, time(14, 0), "Avis néphrologue",                    "effectue"),
            (3, dr1, -65, time(9, 30), "Crise asthmatique – consultation",    "effectue"),
            (3, dr2, -30, time(10, 30),"Renouvellement traitement asthme",    "effectue"),
            (4, dr3, -70, time(8, 0),  "Suivi diabète – HbA1c",               "effectue"),
            (4, dr2, -40, time(11, 0), "Bilan lipidique",                     "effectue"),
            (5, dr2, -55, time(9, 0),  "Suivi hépatite B",                    "effectue"),
            (5, dr1, -25, time(15, 0), "Consultation suivi fibrose hépatique","effectue"),
            (6, dr1, -85, time(10, 0), "Suivi HTA – TA mal contrôlée",        "effectue"),
            (6, dr2, -35, time(9, 0),  "Contrôle tension artérielle",         "effectue"),
            (7, dr3, -60, time(8, 0),  "Suivi diabète + HTA",                 "effectue"),
            (7, dr1, -20, time(14, 30),"Consultation cardiologique",          "effectue"),
            # Annulés
            (0, dr1, -15, time(8, 0),  "Contrôle glycémie",                   "annule"),
            (4, dr3, -10, time(9, 0),  "Renouvellement traitement",           "annule"),
        ]

        for pid, doctor, delta, heure, motif, status in schedule:
            d = today + timedelta(days=delta)
            rdvs_passes.append(Appointment(
                patient=patients[pid], doctor=doctor,
                date=d, heure=heure, motif=motif,
                status=status, created_by=admin,
            ))

        Appointment.objects.bulk_create(rdvs_passes, ignore_conflicts=True)

        # Futurs planifiés (créés normalement)
        futurs = [
            (0, dr1, 7,  time(8, 0),  "Contrôle HbA1c + TA"),
            (1, dr2, 14, time(10, 0), "Résultats CD4 – suivi ARV"),
            (2, dr2, 10, time(9, 0),  "Suivi créatinine + IRC"),
            (3, dr1, 21, time(11, 0), "Évaluation fonction respiratoire"),
            (4, dr3, 5,  time(8, 30), "Renouvellement insuline"),
            (5, dr2, 18, time(9, 30), "Suivi VHB – enzymes hépatiques"),
            (6, dr1, 12, time(10, 0), "Contrôle TA – ajustement traitement"),
            (7, dr3, 9,  time(14, 0), "Bilan diabète + cardio"),
            (2, dr3, 30, time(15, 0), "Avis consultation spécialisée"),
            (0, dr2, 25, time(11, 30),"Évaluation cardiaque préventive"),
        ]

        for pid, doctor, delta, heure, motif in futurs:
            d = today + timedelta(days=delta)
            try:
                rdv, created = Appointment.objects.get_or_create(
                    patient=patients[pid], doctor=doctor, date=d, heure=heure,
                    defaults={"motif": motif, "status": "planifie", "created_by": admin},
                )
            except Exception:
                pass  # conflit d'heure ignoré

        total = Appointment.objects.count()
        self.stdout.write(self.style.SUCCESS(f"    OK {total} rendez-vous"))

    # ──────────────────────────────────────────────────────────────────
    # SUIVIS MÉDICAUX
    # ──────────────────────────────────────────────────────────────────
    def _create_suivis(self, patients, users):
        from suivi_medical.models import SuiviMedical
        from django.db import connection
        self.stdout.write("  Création des suivis médicaux…")

        dr1, dr2, dr3 = users["doctors"]

        # (patient_idx, doctor, type, statut, poids, taille,
        #  tens_sys, tens_dia, glycemie, hemoglobine, cholesterol,
        #  creatinine, cd4, charge_virale, observations, delta_jours)
        data = [
            # Kouyaté Mamadou — diabète + HTA (Docteur 1 et 2)
            (0, dr1, "rdv",    "stable",   88, 170, 140, 88,  7.2,  None, None, None, None, None,
             "Glycémie stable sous Metformine. TA légèrement élevée.", -90),
            (0, dr1, "rdv",    "stable",   87, 170, 135, 85,  6.9,  None, None, None, None, None,
             "Bonne observance. Réduction du sel recommandée.", -60),
            (0, dr2, "direct", "ameliore", 86, 170, 130, 82,  6.5,  None, 2.1,  None, None, None,
             "Amélioration notable. Cholestérol dans les normes.", -30),
            (0, dr1, "rdv",    "stable",   85, 170, 132, 83,  6.7,  None, None, None, None, None,
             "Poursuite du traitement. Prochain RDV dans 4 semaines.", -7),

            # Bah Fatoumata — VIH + anémie (Docteur 2 et 1)
            (1, dr2, "rdv",    "stable",   60, 162, None, None, None, 10.2, None, None, 450, 500,
             "CD4 stables. Charge virale indétectable. Traitement ARV bien toléré.", -75),
            (1, dr1, "direct", "stable",   61, 162, None, None, None, 10.8, None, None, 480, 420,
             "Amélioration hémoglobine. Supplémentation en fer poursuivie.", -45),
            (1, dr2, "rdv",    "stable",   62, 162, None, None, None, 11.0, None, None, 510, 350,
             "CD4 en hausse. Charge virale très basse. Bonne réponse ARV.", -15),

            # Diallo Ibrahima — HTA + IRC (Docteur 2 et 3)
            (2, dr2, "rdv",    "stable",   92, 175, 155, 95, None, None, None, 185, None, None,
             "TA élevée. Créatinine en légère hausse. Ajustement posologie.", -80),
            (2, dr3, "rdv",    "critique", 91, 175, 168, 102, None, None, None, 220, None, None,
             "Détérioration fonction rénale. Créatinine critique. Hospitalisation discutée.", -50),
            (2, dr2, "direct", "stable",   90, 175, 148, 90, None, None, None, 195, None, None,
             "Stabilisation après ajustement traitement diurétique.", -20),

            # Camara Mariama — Asthme (Docteur 1 et 2)
            (3, dr1, "rdv",    "critique", 58, 163, None, None, None, None, None, None, None, None,
             "Crise d'asthme modérée. DEP 55% théorique. Corticoïdes prescrits.", -65),
            (3, dr2, "direct", "ameliore", 59, 163, None, None, None, None, None, None, None, None,
             "Amélioration sous corticoïdes. DEP 75%. Poursuite inhalateur.", -30),
            (3, dr1, "rdv",    "stable",   59, 163, None, None, None, None, None, None, None, None,
             "Asthme bien contrôlé. Technique d'inhalation revue.", -5),

            # Keïta Oumar — Diabète + dyslipidémie (Docteur 3 et 2)
            (4, dr3, "rdv",    "stable",   95, 168, 138, 86, 8.1, None, 2.8, None, None, None,
             "Glycémie toujours élevée. HbA1c 8,1%. Ajustement Metformine.", -70),
            (4, dr2, "rdv",    "stable",   94, 168, 134, 84, 7.8, None, 2.4, None, None, None,
             "Cholestérol amélioré sous statine. Glycémie à surveiller.", -40),
            (4, dr3, "direct", "ameliore", 93, 168, 130, 82, 7.2, None, 2.1, None, None, None,
             "Bonne progression. HbA1c cible atteinte. Maintien traitement.", -10),

            # Touré Aminata — Hépatite B (Docteur 2 et 1)
            (5, dr2, "rdv",    "stable",   65, 165, None, None, None, None, None, None, None, None,
             "ALAT normales. Charge virale VHB faible. Traitement Entécavir poursuivi.", -55),
            (5, dr1, "direct", "stable",   65, 165, None, None, None, None, None, None, None, None,
             "Bilan hépatique stable. Échographie abdominale prescrite.", -25),
            (5, dr2, "rdv",    "stable",   66, 165, None, None, None, None, None, None, None, None,
             "Résultats échographie normaux. Pas de fibrose hépatique significative.", -8),

            # Sylla Aboubacar — HTA (Docteur 1 et 2)
            (6, dr1, "rdv",    "critique", 102, 178, 175, 108, None, None, None, None, None, None,
             "TA très élevée. Patient non observant. Risque AVC. Hospitalisation proposée.", -85),
            (6, dr2, "rdv",    "stable",   100, 178, 158, 96, None, None, None, None, None, None,
             "TA améliorée après reprise traitement. Éducation thérapeutique réalisée.", -35),
            (6, dr1, "direct", "stable",   99, 178, 148, 92, None, None, None, None, None, None,
             "Bonne observance ce mois. TA dans les objectifs.", -5),

            # Barry Kadiatou — Diabète + HTA (Docteur 3 et 1)
            (7, dr3, "rdv",    "stable",   78, 160, 145, 90, 8.5, None, None, None, None, None,
             "Diabète et HTA diagnostiqués cette année. Mise en route traitement.", -60),
            (7, dr1, "rdv",    "stable",   77, 160, 138, 86, 7.9, None, None, None, None, None,
             "Adaptation posologique. Surveillance rapprochée. Glycémie en amélioration.", -30),
            (7, dr3, "direct", "ameliore", 76, 160, 132, 84, 7.4, None, None, None, None, None,
             "Bonne réponse au traitement. HbA1c en baisse.", -10),
        ]

        # Insertion directe via SQL-level pour conserver les dates historiques
        suivis = []
        for row in data:
            (pid, doctor, type_suivi, statut, poids, taille,
             ts, td, glyc, hemo, chol, creat, cd4, cv, obs, delta) = row

            s = SuiviMedical(
                patient=patients[pid], medecin=doctor,
                type_suivi=type_suivi, statut=statut,
                poids=poids, taille=taille,
                tension_systolique=ts, tension_diastolique=td,
                glycemie=glyc, hemoglobine=hemo, cholesterol=chol,
                creatinine=creat, cd4=cd4, charge_virale=cv,
                observations=obs,
            )
            s.save()
            # Mise à jour de created_at en base directement
            SuiviMedical.objects.filter(pk=s.pk).update(
                created_at=timezone.now() + timedelta(days=delta)
            )
            s.refresh_from_db()
            suivis.append(s)

        self.stdout.write(self.style.SUCCESS(f"    OK {len(suivis)} suivis médicaux"))
        return suivis

    # ──────────────────────────────────────────────────────────────────
    # PRESCRIPTIONS
    # ──────────────────────────────────────────────────────────────────
    def _create_prescriptions(self, patients, users, suivis, medications, maladies):
        from pharmacie.models import (
            Prescription, PrescriptionItem, Dispensation,
            DispensationItem, MouvementStock,
        )
        self.stdout.write("  Création des prescriptions et dispensations…")

        dr1, dr2, dr3 = users["doctors"]
        pharma = users["pharma"]

        # Index suivis par patient
        suivis_par_patient = {}
        for s in suivis:
            suivis_par_patient.setdefault(s.patient_id, []).append(s)

        def get_suivi(patient, idx=0):
            lst = suivis_par_patient.get(patient.id, [])
            return lst[idx] if idx < len(lst) else (lst[0] if lst else None)

        # (patient_idx, medecin, suivi_idx, maladie_key, duree, statut, items, dispenser)
        prescriptions_data = [
            # Kouyaté — Diabète + HTA
            (0, dr1, 0, "Diabète de type 2", 30, "active",
             [("Metformine 500mg", "500mg", "2_par_jour", 60),
              ("Amlodipine 5mg",   "5mg",   "1_par_jour", 30)], True),
            (0, dr1, 2, "Hypertension artérielle", 30, "active",
             [("Lisinopril 10mg", "10mg", "1_par_jour", 30)], True),

            # Bah — VIH + Anémie
            (1, dr2, 0, "VIH / SIDA", 30, "active",
             [("Efavirenz 600mg",  "600mg", "1_par_jour", 30),
              ("Lamivudine 150mg", "150mg", "2_par_jour", 60),
              ("Ténofovir 300mg",  "300mg", "1_par_jour", 30)], True),
            (1, dr1, 1, "Anémie chronique", 30, "en_attente",
             [("Fumarate ferreux", "200mg", "2_par_jour", 60)], False),

            # Diallo — HTA + IRC
            (2, dr2, 0, "Hypertension artérielle", 30, "active",
             [("Furosémide 40mg", "40mg", "1_par_jour", 30),
              ("Amlodipine 5mg",  "5mg",  "1_par_jour", 30)], True),

            # Camara — Asthme
            (3, dr1, 0, "Asthme bronchique", 30, "active",
             [("Salbutamol inhalé", "2 bouffées", "au_besoin", 2),
              ("Prednisolone 5mg",  "5mg",         "1_par_jour", 30)], True),

            # Keïta Oumar — Diabète + Dyslipidémie
            (4, dr3, 0, "Diabète de type 2", 30, "active",
             [("Metformine 500mg",   "1000mg", "2_par_jour", 60),
              ("Atorvastatine 20mg", "20mg",   "1_par_jour", 30)], True),

            # Touré — Hépatite B
            (5, dr2, 0, "Hépatite B chronique", 30, "active",
             [("Entécavir 0,5mg", "0,5mg", "1_par_jour", 30)], True),

            # Sylla — HTA
            (6, dr1, 0, "Hypertension artérielle", 30, "active",
             [("Amlodipine 5mg",  "5mg",  "1_par_jour", 30),
              ("Lisinopril 10mg", "10mg", "1_par_jour", 30)], True),

            # Barry — Diabète + HTA
            (7, dr3, 0, "Diabète de type 2", 30, "active",
             [("Metformine 500mg", "500mg", "2_par_jour", 60),
              ("Amlodipine 5mg",   "5mg",   "1_par_jour", 30)], True),
            (7, dr1, 1, "Hypertension artérielle", 60, "active",
             [("Furosémide 40mg", "40mg", "1_par_jour", 30)], False),
        ]

        count_presc = 0
        count_disp = 0

        for (pid, medecin, s_idx, mal_key, duree, statut, items, faire_disp) in prescriptions_data:
            patient = patients[pid]
            suivi   = get_suivi(patient, s_idx)
            maladie = maladies.get(mal_key)

            presc, created = Prescription.objects.get_or_create(
                patient=patient, medecin=medecin,
                suivi_medical=suivi, maladie=maladie, duree_standard=duree,
                defaults={"statut": statut},
            )
            if not created:
                continue
            count_presc += 1

            for (med_nom, dosage, freq, qte) in items:
                med = medications.get(med_nom)
                if med:
                    PrescriptionItem.objects.create(
                        prescription=presc, medication=med,
                        dosage=dosage, frequence=freq, quantite=qte,
                    )

            if faire_disp and pharma:
                periode = (timezone.now() - timedelta(days=30)).date().replace(day=1)
                disp = Dispensation.objects.create(
                    prescription=presc, pharmacien=pharma, periode=periode,
                )
                count_disp += 1
                for item in presc.items.all():
                    lot = item.medication.lots.filter(quantite__gt=0).first()
                    if lot and lot.quantite >= item.quantite:
                        DispensationItem.objects.create(
                            dispensation=disp, medication=item.medication,
                            lot=lot, quantite=item.quantite,
                        )
                        lot.quantite -= item.quantite
                        lot.save()
                        MouvementStock.objects.create(
                            lot=lot, type_mouvement='dispensation',
                            quantite=-item.quantite,
                            utilisateur=pharma, dispensation=disp,
                            reference=f"Dispensation presc.{presc.id}",
                        )

        self.stdout.write(self.style.SUCCESS(
            f"    OK {count_presc} prescriptions, {count_disp} dispensations"
        ))

    # ──────────────────────────────────────────────────────────────────
    # ANALYSES LABO
    # ──────────────────────────────────────────────────────────────────
    def _create_lab_tests(self, patients, users, suivis, maladies):
        from laboratoire.models import LabTest
        self.stdout.write("  Création des analyses de laboratoire…")

        dr1, dr2, dr3 = users["doctors"]
        labo = users["labo"]

        suivis_par_patient = {}
        for s in suivis:
            suivis_par_patient.setdefault(s.patient_id, []).append(s)

        def get_suivi(patient, idx=0):
            lst = suivis_par_patient.get(patient.id, [])
            return lst[idx] if idx < len(lst) else (lst[0] if lst else None)

        # (pid, doc, suivi_idx, type_test, valeur, val2, unite, seuil_min, seuil_max,
        #  status, is_validated, valide_par_labo, resultat_texte, urgence, maladie_key,
        #  notes_medecin, lu)
        tests_data = [
            # Kouyaté — glycémie (critique)
            (0, dr1, 0, "glycemie", 14.5, None, "mmol/L", 3.9, 6.1, "critique", True,  True,
             "Glycémie très élevée. HbA1c 9,2%.", True,  "Diabète de type 2",
             "Glycémie critique. Ajustement posologie Metformine. Insuline discutée.", True),
            # Kouyaté — tension
            (0, dr1, 1, "tension", 142, 90, "mmHg", None, None, "anormal", True, True,
             "TA systolique élevée.", False, "Hypertension artérielle",
             "TA toujours élevée. Renforcer traitement antihypertenseur.", True),

            # Bah — CD4 (normal)
            (1, dr2, 0, "cd4", 510, None, "cells/mm³", 500, None, "normal", True, True,
             "CD4 en hausse. Bon signe immunologique.", False, "VIH / SIDA",
             "CD4 au-dessus de 500. Poursuivre ARV.", True),
            # Bah — hémoglobine (anormal)
            (1, dr1, 1, "hemoglobine", 9.8, None, "g/dL", 12.0, 16.0, "anormal", True, True,
             "Anémie modérée persistante.", False, "Anémie chronique",
             "Hémoglobine basse. Augmenter supplémentation en fer.", True),
            # Bah — charge virale (urgent, en attente)
            (1, dr2, 2, "charge_virale", None, None, "copies/mL", None, 200, "en_attente", False, False,
             "", True, "VIH / SIDA", None, False),

            # Diallo — créatinine (critique)
            (2, dr2, 1, "creatinine", 280, None, "mg/L", None, 115, "critique", True, True,
             "Créatinine très élevée. IRC stade 4.", True, "Insuffisance rénale chronique",
             "Créatinine critique. Consultation néphrologue urgente. Dialyse à envisager.", True),
            # Diallo — NFS (anormal)
            (2, dr2, 0, "nfs", 9.5, None, "g/dL", 12.0, 18.0, "anormal", True, True,
             "Anémie modérée liée à l'IRC.", False, "Insuffisance rénale chronique",
             "Anémie de l'IRC. Érythropoïétine envisagée.", True),

            # Camara — hemoglobine (en attente, urgente)
            (3, dr1, 0, "hemoglobine", None, None, "g/dL", 12.0, 16.0, "en_attente", False, False,
             "", True, "Asthme bronchique", None, False),

            # Keïta — glycémie (anormal)
            (4, dr3, 0, "glycemie", 8.8, None, "mmol/L", 3.9, 6.1, "anormal", True, True,
             "Glycémie encore élevée malgré traitement.", False, "Diabète de type 2",
             "Glycémie en amélioration mais objectif non atteint. Continuer adaptation.", True),
            # Keïta — cholestérol (normal)
            (4, dr3, 2, "cholesterol", 1.9, None, "g/L", None, 2.0, "normal", True, True,
             "Cholestérol total dans les normes sous statine.", False, "Dyslipidémie",
             "Bon contrôle lipidique. Maintenir Atorvastatine.", True),

            # Touré — transaminases (anormal)
            (5, dr2, 0, "transaminases", 78, None, "UI/L", None, 40, "anormal", True, True,
             "ALAT modérément élevées. À surveiller.", False, "Hépatite B chronique",
             "Cytolyse hépatique modérée. Poursuite Entécavir + surveillance.", True),

            # Sylla — tension (critique)
            (6, dr1, 0, "tension", 178, 110, "mmHg", None, None, "critique", True, True,
             "TA très élevée. Risque AVC immédiat.", True, "Hypertension artérielle",
             "TA au niveau critique. Hospitalisation recommandée. ARV ajustés.", True),

            # Barry — glycémie + HbA1c (anormal)
            (7, dr3, 0, "glycemie", 9.2, None, "mmol/L", 3.9, 6.1, "anormal", True, True,
             "Glycémie élevée. HbA1c estimé à 8,5%.", False, "Diabète de type 2",
             "Objectif glycémique non atteint. Renforcer traitement.", True),
            # Barry — en attente
            (7, dr1, 1, "tension", None, None, "mmHg", None, None, "en_attente", False, False,
             "", False, "Hypertension artérielle", None, False),
        ]

        count = 0
        for row in tests_data:
            (pid, doc, s_idx, type_test, valeur, val2, unite,
             seuil_min, seuil_max, status, is_val, valide_labo,
             resultat, urgence, mal_key, notes, lu) = row

            patient = patients[pid]
            suivi   = get_suivi(patient, s_idx)
            maladie = maladies.get(mal_key)
            if not suivi:
                continue

            validated_by = labo if valide_labo else None
            validated_at = timezone.now() - timedelta(days=random.randint(1, 30)) if is_val else None

            test = LabTest(
                patient=patient, suivi=suivi, prescripteur=doc,
                technicien=labo if valide_labo else None,
                maladie=maladie,
                type_test=type_test, valeur=valeur, valeur_secondaire=val2,
                unite=unite, seuil_min=seuil_min, seuil_max=seuil_max,
                status=status, urgence=urgence, resultat=resultat or "",
                is_validated=is_val, validated_by=validated_by, validated_at=validated_at,
                lu_par_medecin=lu, notes_medecin=notes,
                date_lecture=validated_at if lu else None,
                is_abnormal=(status in ("anormal", "critique")),
            )
            test.save()
            count += 1

        self.stdout.write(self.style.SUCCESS(f"    OK {count} analyses de laboratoire"))

    # ──────────────────────────────────────────────────────────────────
    # ALERTES & NOTIFICATIONS
    # ──────────────────────────────────────────────────────────────────
    def _create_alerts_notifications(self, patients, users):
        from alertes_notifications.models import Alert, Notification
        self.stdout.write("  Création des alertes et notifications…")

        dr1, dr2, dr3 = users["doctors"]
        nurses        = users["nurses"]
        admin         = users["admin"]
        all_staff     = [dr1, dr2, dr3] + nurses + [admin]

        alerts_data = [
            # (patient_idx, alert_type, source, message, is_resolved, acknowledged)
            (0, "critical", "suivi_medical",
             "Glycémie critique : 14,5 mmol/L (norme : 3,9–6,1). Kouyaté Mamadou. Intervention requise.",
             False, True),
            (2, "critical", "laboratoire",
             "Créatinine critique : 280 mg/L (norme ≤ 115). Diallo Ibrahima. IRC stade 4 – dialyse urgente.",
             False, False),
            (6, "critical", "suivi_medical",
             "Tension artérielle critique : 178/110 mmHg. Sylla Aboubacar. Risque AVC immédiat.",
             False, False),
            (0, "warning", "suivi_medical",
             "Tension artérielle élevée : 142/90 mmHg. Kouyaté Mamadou. Ajustement traitement nécessaire.",
             True, True),
            (1, "warning", "laboratoire",
             "Hémoglobine basse : 9,8 g/dL (norme 12–16). Bah Fatoumata. Anémie modérée persistante.",
             False, True),
            (3, "warning", "suivi_medical",
             "Crise asthmatique modérée. Camara Mariama. DEP 55% théorique. Corticoïdes prescrits.",
             True, True),
            (4, "warning", "suivi_medical",
             "Glycémie élevée : 8,8 mmol/L. Keïta Oumar. Objectif glycémique non atteint.",
             False, False),
            (5, "warning", "laboratoire",
             "Transaminases élevées : 78 UI/L (norme ≤ 40). Touré Aminata. Cytolyse hépatique modérée.",
             False, True),
            (7, "warning", "suivi_medical",
             "Glycémie élevée : 9,2 mmol/L. Barry Kadiatou. Diabète mal contrôlé.",
             False, False),
            (2, "warning", "renouvellement",
             "Renouvellement imminent du traitement antihypertenseur de Diallo Ibrahima dans 5 jours.",
             False, False),
            (0, "info", "stock_pharmacie",
             "Stock Fumarate ferreux critique : 3 unités restantes (seuil 10). Réapprovisionnement requis.",
             False, False),
            (1, "info", "rdv",
             "Rappel rendez-vous CD4 – Bah Fatoumata dans 14 jours. Dr. Camara.",
             True, True),
        ]

        alerts_created = []
        for (pid, atype, source, message, is_resolved, is_ack) in alerts_data:
            patient = patients[pid]
            a = Alert(
                patient=patient, alert_type=atype, source=source, message=message,
            )
            if is_ack:
                a.acknowledged_by = dr1
                a.acknowledged_at  = timezone.now() - timedelta(hours=random.randint(1, 48))
            if is_resolved:
                a.is_resolved  = True
                a.resolved_by  = dr1
                a.resolved_at  = timezone.now() - timedelta(hours=random.randint(1, 24))
                if not a.acknowledged_by:
                    a.acknowledged_by = dr1
                    a.acknowledged_at  = a.resolved_at - timedelta(hours=1)
            a.save()
            alerts_created.append(a)

        # Notifications ciblées
        notifs_data = [
            # (user, title, message, level, is_read)
            (dr1, "Alerte critique — Kouyaté Mamadou",
             "Glycémie critique (14,5 mmol/L) enregistrée. Consultation urgente recommandée.",
             "urgent", False),
            (dr2, "Alerte critique — Diallo Ibrahima",
             "Créatinine à 280 mg/L. IRC stade 4. Nephrologue à contacter immédiatement.",
             "urgent", False),
            (dr1, "Alerte critique — Sylla Aboubacar",
             "TA à 178/110 mmHg. Risque cardiovasculaire majeur. Hospitalisation recommandée.",
             "urgent", False),
            (dr2, "Résultat labo disponible — Bah Fatoumata",
             "CD4 : 510 cells/mm³. Hémoglobine : 9,8 g/dL. Résultats validés par le labo.",
             "warning", False),
            (dr3, "Résultat labo disponible — Keïta Oumar",
             "Glycémie : 8,8 mmol/L. Cholestérol : 1,9 g/L. Veuillez interpréter.",
             "warning", False),
            (dr1, "Renouvellement imminent — Diallo Ibrahima",
             "Le traitement antihypertenseur de Diallo Ibrahima doit être renouvelé dans 5 jours.",
             "warning", True),
            (dr2, "Résultat labo — Touré Aminata",
             "Transaminases ALAT : 78 UI/L (norme ≤ 40). Hépatite B active – surveillance renforcée.",
             "warning", False),
            (nurses[0], "Alerte — Sylla Aboubacar",
             "TA critique. Prévoir prise en charge infirmière urgente – mesure TA toutes les 2h.",
             "urgent", False),
            (nurses[1], "Alerte — Kouyaté Mamadou",
             "Glycémie critique. Surveillance glycémique horaire recommandée.",
             "urgent", False),
            (dr3, "Suivi — Barry Kadiatou",
             "HbA1c estimée à 8,5%. Glycémie non contrôlée malgré traitement. Intensifier.",
             "warning", True),
            (dr1, "Analyse urgente en attente — Camara Mariama",
             "NFS urgente prescrite pour Camara Mariama. Résultats non encore saisis par le labo.",
             "warning", False),
            (dr2, "Charge virale urgente — Bah Fatoumata",
             "Analyse charge virale VIH prescrite en urgence. En attente résultats laboratoire.",
             "urgent", False),
            (admin, "Rupture de stock — Fumarate ferreux",
             "Stock Fumarate ferreux critique : 3 unités (seuil 10). Commande à lancer immédiatement.",
             "urgent", False),
            (users["pharma"], "Rupture de stock — Fumarate ferreux",
             "Stock Fumarate ferreux : 3 unités restantes. Réapprovisionnement requis en urgence.",
             "urgent", False),
            (users["labo"], "Analyses urgentes en attente",
             "2 analyses urgentes en attente de traitement : charge virale VIH (Bah) + NFS (Camara).",
             "urgent", False),
            # Notifications patients
            (users["patient_accounts"][0], "Renouvellement traitement",
             "Votre traitement Diabète/HTA doit être renouvelé. Présentez-vous à la pharmacie.",
             "warning", True),
            (users["patient_accounts"][1], "Résultats CD4 disponibles",
             "Vos résultats CD4 sont disponibles. Consultez votre médecin pour l'interprétation.",
             "info", False),
            (users["patient_accounts"][2], "Rendez-vous à venir",
             "Rappel : vous avez un rendez-vous avec le Dr. Camara dans 10 jours.",
             "info", False),
        ]

        for (user, title, message, level, is_read) in notifs_data:
            n = Notification.objects.create(
                user=user, title=title, message=message, level=level, is_read=is_read,
            )

        total_alerts = Alert.objects.count()
        total_notifs = Notification.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"    OK {total_alerts} alertes, {total_notifs} notifications"
        ))

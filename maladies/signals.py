from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PatientMaladie
from .services import get_patient_maladie_summary


# =========================
# POST SAVE PATIENT MALADIE
# =========================
@receiver(post_save, sender=PatientMaladie)
def patient_maladie_post_save(sender, instance, created, **kwargs):
    # ici tu peux ajouter notifications futures
    get_patient_maladie_summary(instance.patient)


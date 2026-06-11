from django.db import models

# Create your models here.


class Maladie(models.Model):

    TYPE_CHOICES = (
       ('infectieuse', 'Infectieuse'),
       ('metabolique', 'Métabolique'),
       ('respiratoire', 'Respiratoire'),
       ('cardiovasculaire', 'cardiovasculaire'),
       ('neurologique', 'Neurologique'),
       ('auto-immune', 'auto-immune'),
       ('rénale','rénale' ),
       ('autre', 'Autre'),

)
    type = models.CharField(max_length=20,choices=TYPE_CHOICES,default='autre')
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.nom

class PatientMaladie(models.Model):

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('stable', 'Stable'),
        ('guérie', 'Guérie'),
    )

    patient = models.ForeignKey(
        'patients.Patient',
        on_delete=models.CASCADE,
        related_name='maladies'
    )

    maladie = models.ForeignKey(
        Maladie,
        on_delete=models.CASCADE,
        related_name='patients'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    date_diagnostic = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    observations = models.TextField(blank=True)

    class Meta:
        unique_together = ('patient', 'maladie')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.patient} - {self.maladie} ({self.status})"
    
class SeuilAlerte(models.Model):

    patient_maladie = models.ForeignKey(
        PatientMaladie,
        on_delete=models.CASCADE,
        related_name='seuils'
    )

    indicateur = models.CharField(max_length=100)
    min_valeur = models.FloatField(null=True, blank=True)
    max_valeur = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Seuil d'alerte"
        verbose_name_plural = "Seuils d'alerte"

    def __str__(self):
        return f"{self.indicateur} - {self.patient_maladie}"        
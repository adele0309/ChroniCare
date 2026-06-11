import uuid

from django import forms
from django.forms import inlineformset_factory

from .models import Medication, MedicationLot, Prescription, PrescriptionItem


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model  = Prescription
        fields = ['duree_standard']
        widgets = {
            'duree_standard': forms.Select(attrs={'class': 'form-select'}),
        }


class PrescriptionCreateForm(forms.ModelForm):
    """Formulaire de création d'une prescription depuis un suivi médical."""
    class Meta:
        model  = Prescription
        fields = ['maladie', 'duree_standard']
        widgets = {
            'maladie':       forms.Select(attrs={'class': 'form-select'}),
            'duree_standard': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, patient=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['maladie'].required = False
        self.fields['maladie'].empty_label = '— Aucune (prescription générale) —'
        if patient:
            from maladies.models import PatientMaladie
            maladie_ids = PatientMaladie.objects.filter(
                patient=patient
            ).values_list('maladie_id', flat=True)
            from maladies.models import Maladie
            self.fields['maladie'].queryset = Maladie.objects.filter(pk__in=maladie_ids)


class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model  = PrescriptionItem
        fields = ['medication', 'dosage', 'frequence', 'quantite']
        widgets = {
            'medication': forms.Select(attrs={'class': 'form-select'}),
            'dosage':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 500mg'}),
            'frequence':  forms.Select(attrs={'class': 'form-select'}),
            'quantite':   forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }


PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=3,
    can_delete=True,
)


class MedicationForm(forms.ModelForm):
    class Meta:
        model  = Medication
        fields = ['nom', 'unite', 'stock_minimum', 'prix']
        widgets = {
            'nom':          forms.TextInput(attrs={'class': 'form-control'}),
            'unite':        forms.Select(attrs={'class': 'form-select'}),
            'stock_minimum': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'prix':         forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.01'}),
        }


class MedicationLotForm(forms.ModelForm):
    class Meta:
        model  = MedicationLot
        fields = ['medication', 'numero_lot', 'quantite', 'date_expiration', 'date_reception']
        widgets = {
            'medication':     forms.Select(attrs={'class': 'form-select'}),
            'numero_lot':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Laissez vide pour générer automatiquement'}),
            'quantite':       forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'date_expiration': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_reception':  forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def clean_numero_lot(self):
        numero = self.cleaned_data.get('numero_lot', '').strip()
        if not numero:
            numero = f"LOT-{uuid.uuid4().hex[:8].upper()}"
        return numero

from rest_framework import serializers
from .models import SuiviMedical


class SuiviMedicalSerializer(serializers.ModelSerializer):

    patient_nom = serializers.SerializerMethodField()
    medecin_nom = serializers.CharField(source='medecin.get_full_name', read_only=True)
    statut_label = serializers.CharField(source='get_statut_display', read_only=True)
    imc = serializers.FloatField(read_only=True)

    class Meta:
        model = SuiviMedical
        fields = [
            'id',
            'type_suivi',
            'appointment',
            'patient', 'patient_nom',
            'medecin', 'medecin_nom',
            'poids', 'taille', 'imc',
            'tension_systolique', 'tension_diastolique',
            'glycemie',
            'hemoglobine', 'cholesterol',
            'creatinine', 'uree', 'transaminases',
            'cd4', 'charge_virale',
            'observations',
            'statut', 'statut_label',
            'created_at',
        ]
        read_only_fields = ['imc', 'created_at']

    def get_patient_nom(self, obj):
        return f"{obj.patient.nom} {obj.patient.prenom}"

    def validate(self, data):
        if data.get('glycemie') and data['glycemie'] > 2.0:
            data['statut'] = 'critique'
        if data.get('cd4') and data['cd4'] < 200:
            data['statut'] = 'critique'
        if data.get('charge_virale') and data['charge_virale'] > 1000:
            data['statut'] = 'critique'
        if data.get('hemoglobine') is not None and data['hemoglobine'] < 7.0:
            data['statut'] = 'critique'
        if data.get('cholesterol') is not None and data['cholesterol'] > 3.0:
            data['statut'] = 'critique'
        if data.get('creatinine') is not None and data['creatinine'] > 20.0:
            data['statut'] = 'critique'
        return data

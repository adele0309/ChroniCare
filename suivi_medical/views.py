from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from rest_framework import viewsets

from core.utils import log_action
from .models import SuiviMedical
from .serializers import SuiviMedicalSerializer
from .forms import SuiviMedicalCreateForm, SuiviMedicalUpdateForm
from .services import create_suivi_from_rdv, check_alerts_suivi
from appointments.models import Appointment
from pharmacie.forms import PrescriptionCreateForm, PrescriptionItemFormSet
from users.permissions import IsDoctorOrNurseOrAdmin
from users.decorators import role_required


# ═══════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════

class SuiviMedicalViewSet(viewsets.ModelViewSet):
    queryset = SuiviMedical.objects.all()
    permission_classes = [IsDoctorOrNurseOrAdmin]
    serializer_class = SuiviMedicalSerializer

    def perform_create(self, serializer):
        suivi = serializer.save()
        log_action(
            self.request.user,
            "CREATE_SUIVI_MEDICAL",
            f"Suivi ajouté pour {suivi.patient.nom}",
            "SUIVI_MEDICAL",
        )

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return SuiviMedical.objects.none()
        qs = SuiviMedical.objects.select_related("patient", "medecin", "appointment")
        role = getattr(user, "role", None)
        if role == "patient":
            return qs.filter(patient__compte_patient=user)
        if role == "doctor":
            return qs.filter(medecin=user)
        patient_id = self.request.query_params.get("patient")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs


# ═══════════════════════════════════════════════════════════════
# HTML views
# ═══════════════════════════════════════════════════════════════

@login_required
def suivi_list(request):
    role = getattr(request.user, "role", None)
    qs = SuiviMedical.objects.select_related("patient", "medecin").all()

    if role == "patient":
        qs = qs.filter(patient__compte_patient=request.user)
    elif role == "doctor":
        qs = qs.filter(medecin=request.user)

    # Filtres GET
    patient_nom  = request.GET.get("patient", "").strip()
    statut       = request.GET.get("statut", "").strip()
    date_filter  = request.GET.get("date", "").strip()

    if patient_nom:
        qs = qs.filter(
            Q(patient__nom__icontains=patient_nom) |
            Q(patient__prenom__icontains=patient_nom)
        )
    if statut:
        qs = qs.filter(statut=statut)
    if date_filter:
        try:
            qs = qs.filter(created_at__date=date_filter)
        except Exception:
            pass

    return render(request, "suivi_medical/suivi_list.html", {
        "suivis": qs,
        "statut_choices": SuiviMedical.STATUT_CHOICES,
        "page_title": "Suivi médical",
    })


@login_required
def suivi_detail(request, pk):
    suivi = get_object_or_404(SuiviMedical, pk=pk)
    role  = getattr(request.user, "role", None)
    # Un patient ne peut voir que ses propres suivis
    if role == "patient" and suivi.patient.compte_patient != request.user:
        messages.error(request, "Accès non autorisé.")
        return redirect("suivi-list")
    return render(request, "suivi_medical/suivi_detail.html", {
        "suivi": suivi,
        "page_title": f"Suivi — {suivi.patient.nom} {suivi.patient.prenom}",
    })


@role_required("admin", "doctor", "nurse")
def suivi_create(request):
    from patients.models import Patient
    patient_id  = request.GET.get("patient")
    patient_obj = None
    initial     = {}

    if patient_id:
        try:
            patient_obj           = Patient.objects.get(pk=patient_id)
            initial["patient"]    = patient_id
            initial["type_suivi"] = "direct"
        except Patient.DoesNotExist:
            pass

    form = SuiviMedicalCreateForm(request.POST or None, initial=initial)
    if form.is_valid():
        type_suivi = form.cleaned_data["type_suivi"]

        if type_suivi == "rdv":
            rdv    = form.cleaned_data["appointment"]
            vitals = {
                k: form.cleaned_data.get(k)
                for k in [
                    "poids", "taille",
                    "tension_systolique", "tension_diastolique",
                    "glycemie",
                    "cholesterol", "creatinine", "uree",
                    "transaminases", "hemoglobine",
                    "cd4", "charge_virale",
                    "observations", "statut",
                ]
            }
            suivi = create_suivi_from_rdv(rdv, vitals)
        else:
            suivi = SuiviMedical(
                type_suivi="direct",
                patient=form.cleaned_data["patient"],
                medecin=form.cleaned_data.get("medecin") or request.user,
                poids=form.cleaned_data.get("poids"),
                taille=form.cleaned_data.get("taille"),
                tension_systolique=form.cleaned_data.get("tension_systolique"),
                tension_diastolique=form.cleaned_data.get("tension_diastolique"),
                glycemie=form.cleaned_data.get("glycemie"),
                cholesterol=form.cleaned_data.get("cholesterol"),
                creatinine=form.cleaned_data.get("creatinine"),
                uree=form.cleaned_data.get("uree"),
                transaminases=form.cleaned_data.get("transaminases"),
                hemoglobine=form.cleaned_data.get("hemoglobine"),
                cd4=form.cleaned_data.get("cd4"),
                charge_virale=form.cleaned_data.get("charge_virale"),
                observations=form.cleaned_data.get("observations"),
                statut=form.cleaned_data.get("statut", "stable"),
            )
            suivi.save()
            check_alerts_suivi(suivi)

        messages.success(request, "Suivi créé avec succès.")
        return redirect("patient-detail", pk=suivi.patient.id)

    return render(request, "suivi_medical/suivi_form.html", {
        "form": form,
        "patient_obj": patient_obj,
        "page_title": "Nouveau suivi médical",
    })


@role_required("admin", "doctor", "nurse")
def suivi_update(request, pk):
    suivi = get_object_or_404(SuiviMedical, pk=pk)
    form  = SuiviMedicalUpdateForm(request.POST or None, instance=suivi)
    if form.is_valid():
        suivi = form.save()
        check_alerts_suivi(suivi)
        messages.success(request, "Suivi mis à jour.")
        return redirect("suivi-detail", pk=suivi.pk)
    return render(request, "suivi_medical/suivi_form.html", {
        "form":       form,
        "suivi":      suivi,
        "page_title": f"Modifier le suivi — {suivi.patient.nom} {suivi.patient.prenom}",
    })


@role_required("admin", "doctor", "nurse")
def suivi_delete(request, pk):
    suivi = get_object_or_404(SuiviMedical, pk=pk)
    if request.method == "POST":
        patient_pk = suivi.patient.id
        suivi.delete()
        messages.success(request, "Suivi supprimé.")
        return redirect("patient-detail", pk=patient_pk)
    return render(request, "suivi_medical/suivi_confirm_delete.html", {
        "suivi":      suivi,
        "page_title": "Supprimer le suivi",
    })


@role_required("admin", "doctor", "nurse")
def create_suivi_from_rdv_view(request, rdv_id):
    rdv  = get_object_or_404(Appointment, id=rdv_id)
    form = SuiviMedicalCreateForm(request.POST or None,
                                  initial={"type_suivi": "rdv", "appointment": rdv_id})
    if form.is_valid():
        suivi = create_suivi_from_rdv(rdv, form.cleaned_data)
        return redirect("patient-detail", pk=suivi.patient.id)
    return render(request, "suivi_medical/suivi_form.html", {
        "form":       form,
        "page_title": f"Suivi pour {rdv.patient}",
    })


@role_required("admin", "doctor")
def creer_prescription(request, pk):
    suivi   = get_object_or_404(SuiviMedical, pk=pk)
    patient = suivi.patient
    if request.method == "POST":
        form    = PrescriptionCreateForm(patient, request.POST)
        formset = PrescriptionItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            prescription               = form.save(commit=False)
            prescription.statut        = "en_attente"
            prescription.patient       = patient
            prescription.suivi_medical = suivi
            prescription.medecin       = suivi.medecin or request.user
            prescription.save()
            formset.instance = prescription
            formset.save()
            messages.success(request, "Prescription créée.")
            return redirect("prescription-detail", pk=prescription.id)
    else:
        form    = PrescriptionCreateForm(patient)
        formset = PrescriptionItemFormSet()
    return render(request, "pharmacie/prescription_create.html", {
        "form": form, "formset": formset, "suivi": suivi, "patient": patient,
    })

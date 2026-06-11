from django.shortcuts import render, get_object_or_404, redirect
from rest_framework import viewsets
from core.utils import log_action
from .models import Maladie, PatientMaladie, SeuilAlerte
from .serializers import MaladieSerializer, PatientMaladieSerializer, SeuilAlerteSerializer
from .forms import MaladieForm, PatientMaladieForm, PatientMaladieUpdateForm, SeuilAlerteFormSet
from users.permissions import IsDoctorOrNurseOrAdmin
from users.decorators import role_required


# ============================================================
# API ViewSets
# ============================================================

class MaladieViewSet(viewsets.ModelViewSet):
    queryset = Maladie.objects.all()
    permission_classes = [IsDoctorOrNurseOrAdmin]
    serializer_class = MaladieSerializer


class SeuilAlerteViewSet(viewsets.ModelViewSet):
    queryset = SeuilAlerte.objects.all()
    permission_classes = [IsDoctorOrNurseOrAdmin]
    serializer_class = SeuilAlerteSerializer


class PatientMaladieViewSet(viewsets.ModelViewSet):
    queryset = PatientMaladie.objects.select_related('patient', 'maladie')
    permission_classes = [IsDoctorOrNurseOrAdmin]
    serializer_class = PatientMaladieSerializer

    def perform_create(self, serializer):
        pm = serializer.save()
        log_action(
            self.request.user,
            "CREATE_MALADIE",
            f"MALADIE {pm.maladie.nom} ajoutée pour {pm.patient.nom} {pm.patient.prenom}",
            "MALADIE"
        )

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == 'patient':
            qs = qs.filter(patient__compte_patient=user)
        maladie_type = self.request.query_params.get('type')
        if maladie_type:
            qs = qs.filter(maladie__type=maladie_type)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


# ============================================================
# HTML views — décorateurs alignés sur MaladieViewSet : IsDoctorOrNurseOrAdmin
# ============================================================

@role_required("admin", "doctor", "nurse")
def maladie_list(request):
    maladies = Maladie.objects.all()
    nom = request.GET.get('nom')
    type_filter = request.GET.get('type')
    if nom:
        maladies = maladies.filter(nom__icontains=nom)
    if type_filter:
        maladies = maladies.filter(type=type_filter)
    return render(request, "maladies/maladie_list.html", {
        "maladies": maladies,
        "type_choices": Maladie.TYPE_CHOICES,
        "page_title": "Maladies chroniques",
    })


@role_required("admin", "doctor", "nurse")
def maladie_create(request):
    if request.method == "POST":
        form = MaladieForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("maladie-list")
    else:
        form = MaladieForm()
    return render(request, "maladies/maladie_form.html", {
        "form": form,
        "page_title": "Nouvelle maladie",
    })


@role_required("admin", "doctor", "nurse")
def maladie_detail(request, pk):
    maladie = get_object_or_404(Maladie, pk=pk)
    patient_maladies = PatientMaladie.objects.filter(maladie=maladie).select_related('patient')
    return render(request, "maladies/maladie_detail.html", {
        "maladie": maladie,
        "patient_maladies": patient_maladies,
        "page_title": maladie.nom,
    })


@role_required("admin", "doctor", "nurse")
def maladie_update(request, pk):
    maladie = get_object_or_404(Maladie, pk=pk)
    if request.method == "POST":
        form = MaladieForm(request.POST, instance=maladie)
        if form.is_valid():
            form.save()
            return redirect("maladie-list")
    else:
        form = MaladieForm(instance=maladie)
    return render(request, "maladies/maladie_form.html", {
        "form": form,
        "maladie": maladie,
        "page_title": f"Modifier : {maladie.nom}",
    })


@role_required("admin", "doctor", "nurse")
def maladie_delete(request, pk):
    maladie = get_object_or_404(Maladie, pk=pk)
    if request.method == "POST":
        maladie.delete()
        return redirect("maladie-list")
    return render(request, "maladies/maladie_confirm_delete.html", {
        "maladie": maladie,
        "page_title": f"Supprimer {maladie.nom}",
    })


@role_required("admin", "doctor", "nurse")
def patient_maladie_list(request):
    data = PatientMaladie.objects.select_related('patient', 'maladie').all()
    status_filter = request.GET.get('status')
    if status_filter:
        data = data.filter(status=status_filter)
    return render(request, 'maladies/patient_maladie_list.html', {
        'data': data,
        'status_choices': PatientMaladie.STATUS_CHOICES,
        'page_title': "Patients — Maladies",
    })


@role_required("admin", "doctor", "nurse")
def patient_maladie_create(request):
    from patients.models import Patient
    patient_id = request.GET.get('patient')
    patient_obj = None
    initial = {}
    if patient_id:
        try:
            patient_obj = Patient.objects.get(pk=patient_id)
            initial['patient'] = patient_id
        except Patient.DoesNotExist:
            pass
    form = PatientMaladieForm(request.POST or None, initial=initial)
    if form.is_valid():
        pm = form.save()
        return redirect('patient-detail', pk=pm.patient.id)
    return render(request, 'maladies/patient_maladie_form.html', {
        'form': form,
        'patient_obj': patient_obj,
        'page_title': "Ajouter une maladie chronique",
    })


@role_required("admin", "doctor", "nurse")
def patient_maladie_update(request, pk):
    pm = get_object_or_404(
        PatientMaladie.objects.select_related('patient', 'maladie'),
        pk=pk,
    )
    form = PatientMaladieUpdateForm(request.POST or None, instance=pm)
    seuil_formset = SeuilAlerteFormSet(request.POST or None, instance=pm)
    if request.method == 'POST':
        if form.is_valid() and seuil_formset.is_valid():
            form.save()
            seuil_formset.save()
            return redirect('patient-detail', pk=pm.patient.id)
    return render(request, 'maladies/patient_maladie_form.html', {
        'form': form,
        'seuil_formset': seuil_formset,
        'pm': pm,
        'page_title': f"{pm.maladie.nom} — {pm.patient.nom} {pm.patient.prenom}",
    })


@role_required("admin", "doctor", "nurse")
def patient_maladie_delete(request, pk):
    pm = get_object_or_404(
        PatientMaladie.objects.select_related('patient', 'maladie'),
        pk=pk,
    )
    if request.method == 'POST':
        patient_pk = pm.patient.id
        pm.delete()
        return redirect('patient-detail', pk=patient_pk)
    return render(request, 'maladies/patient_maladie_confirm_delete.html', {
        'pm': pm,
        'page_title': f"Supprimer l'association",
    })

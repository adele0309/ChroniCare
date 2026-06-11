from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from reportlab.pdfgen import canvas

from core.utils import log_action
from users.permissions import IsPharmacistOrAdmin, IsDoctorOrAdmin
from users.decorators import role_required

from .models import (
    Medication, MedicationLot, Prescription,
    Dispensation, MouvementStock,
)
from .serializers import (
    MedicationSerializer, MedicationLotSerializer,
    PrescriptionSerializer, DispensationSerializer,
)
from .forms import PrescriptionForm, MedicationLotForm, MedicationForm
from .services import deliver_prescription_service, check_stock_disponible


# ============================================================
# API ViewSets
# ============================================================

class MedicationViewSet(viewsets.ModelViewSet):
    serializer_class = MedicationSerializer
    permission_classes = [IsPharmacistOrAdmin]

    def get_queryset(self):
        return Medication.objects.prefetch_related('lots')

    @action(detail=False, methods=['get'], url_path='stock-critique')
    def stock_critique(self, request):
        meds = [m for m in Medication.objects.all() if m.est_en_rupture]
        return Response(self.get_serializer(meds, many=True).data)


class MedicationLotViewSet(viewsets.ModelViewSet):
    serializer_class = MedicationLotSerializer
    permission_classes = [IsPharmacistOrAdmin]

    def get_queryset(self):
        qs = MedicationLot.objects.select_related('medication')
        medication_id = self.request.query_params.get('medication')
        if medication_id:
            qs = qs.filter(medication_id=medication_id)
        if self.request.query_params.get('expire_bientot') == 'true':
            limite = timezone.now().date() + timedelta(days=30)
            qs = qs.filter(date_expiration__lte=limite, quantite__gt=0)
        return qs


class PrescriptionViewSet(viewsets.ModelViewSet):
    serializer_class = PrescriptionSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsDoctorOrAdmin()]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        qs = Prescription.objects.select_related('patient', 'medecin', 'maladie').prefetch_related('items')
        if role == 'patient':
            return qs.filter(patient__compte_patient=user)
        if role == 'doctor':
            return qs.filter(medecin=user)
        if role == 'pharmacist':
            # Pharmacist sees en_attente + active (upcoming renewals)
            return qs.filter(statut__in=['en_attente', 'active'])
        if role == 'admin':
            patient_id = self.request.query_params.get('patient')
            if patient_id:
                qs = qs.filter(patient_id=patient_id)
            statut = self.request.query_params.get('statut')
            if statut:
                qs = qs.filter(statut=statut)
            return qs
        return Prescription.objects.none()

    def perform_create(self, serializer):
        serializer.save(medecin=self.request.user)


class DispensationViewSet(viewsets.ModelViewSet):
    serializer_class = DispensationSerializer
    permission_classes = [IsPharmacistOrAdmin]

    def get_queryset(self):
        return Dispensation.objects.select_related(
            'prescription__patient', 'pharmacien'
        ).prefetch_related('items__medication')

    def create(self, request):
        """Délègue au service pour garantir FIFO, stock et atomicité."""
        prescription_id = request.data.get('prescription')
        if not prescription_id:
            return Response({'detail': 'Prescription requise.'}, status=status.HTTP_400_BAD_REQUEST)
        prescription = get_object_or_404(Prescription, pk=prescription_id)
        dispensation, erreur = deliver_prescription_service(prescription, request.user)
        if erreur:
            return Response({'detail': erreur}, status=status.HTTP_400_BAD_REQUEST)
        log_action(
            request.user,
            "DELIVER_MEDICINE",
            f"Médicament délivré pour {dispensation.prescription.patient.nom}",
            "PHARMACIE",
        )
        serializer = self.get_serializer(dispensation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ============================================================
# HTML views
# ============================================================

@role_required("pharmacist", "admin")
def pharmacie_dashboard(request):
    urgentes_qs = Prescription.objects.filter(
        statut__in=['en_attente', 'active'],
        date_prochain_renouvellement__lte=timezone.now().date() + timedelta(days=7),
    ).select_related('patient')
    medications_critique = [m for m in Medication.objects.prefetch_related('lots') if m.est_en_rupture]
    dispensations_recentes = Dispensation.objects.select_related(
        'prescription__patient', 'pharmacien'
    )[:5]
    return render(request, "pharmacie/dashboard.html", {
        "prescriptions_urgentes":  urgentes_qs[:5],
        "medications_critique":    medications_critique,
        "dispensations_recentes":  dispensations_recentes,
        "nb_renouvellements":      urgentes_qs.count(),
        "nb_ruptures":             len(medications_critique),
    })


@login_required
def prescription_list(request):
    user = request.user
    role = getattr(user, 'role', None)
    qs = Prescription.objects.select_related('patient', 'medecin').prefetch_related('items__medication')
    if role == 'patient':
        qs = qs.filter(patient__compte_patient=user)
    elif role == 'doctor':
        qs = qs.filter(medecin=user)
    elif role == 'pharmacist':
        qs = qs.filter(statut__in=['en_attente', 'active'])
    elif role != 'admin':
        qs = Prescription.objects.none()
    return render(request, "pharmacie/prescription_list.html", {"prescriptions": qs})


@role_required("pharmacist", "admin")
def medication_list(request):
    medications = Medication.objects.prefetch_related('lots')
    lots = MedicationLot.objects.select_related('medication').order_by('date_expiration')
    return render(request, "pharmacie/medication_list.html", {
        "medications": medications,
        "lots":        lots,
    })


@role_required("pharmacist", "admin")
def dispensation_list(request):
    dispensations = Dispensation.objects.select_related(
        'prescription__patient', 'pharmacien'
    ).prefetch_related('items__medication')
    return render(request, "pharmacie/dispensation_list.html", {
        "dispensations": dispensations,
    })


@login_required
def prescription_detail(request, pk):
    user = request.user
    role = getattr(user, 'role', None)
    if role not in ('admin', 'doctor', 'pharmacist', 'patient'):
        raise PermissionDenied
    prescription = get_object_or_404(
        Prescription.objects.select_related('patient', 'medecin', 'maladie', 'suivi_medical')
        .prefetch_related('items__medication', 'dispensations__pharmacien'),
        pk=pk,
    )
    if role == 'patient':
        patient_user = getattr(prescription.patient, 'compte_patient', None)
        if patient_user is None or patient_user.pk != user.pk:
            raise PermissionDenied
    ruptures = check_stock_disponible(prescription) if role != 'patient' else []
    return render(request, "pharmacie/prescription_detail.html", {
        "prescription": prescription,
        "ruptures":     ruptures,
    })


@role_required("pharmacist", "admin")
def medication_create(request):
    if request.method == "POST":
        form = MedicationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('medication-list')
    else:
        form = MedicationForm()
    return render(request, 'pharmacie/medication_form.html', {'form': form})


@role_required("pharmacist", "admin")
def add_lot(request):
    if request.method == "POST":
        form = MedicationLotForm(request.POST)
        if form.is_valid():
            lot = form.save()
            MouvementStock.objects.create(
                lot=lot,
                type_mouvement='reception',
                quantite=lot.quantite,
                utilisateur=request.user,
                reference=f"Réception lot {lot.numero_lot}",
            )
            return redirect('medication-list')
    else:
        form = MedicationLotForm()
    return render(request, "pharmacie/lot_form.html", {"form": form})


@role_required("pharmacist", "admin")
def delete_lot(request, pk):
    lot = get_object_or_404(MedicationLot, pk=pk)
    if request.method == "POST":
        lot.delete()
        return redirect('medication-list')
    return render(request, "pharmacie/confirm_delete.html", {"objet": lot, "type": "lot"})


@role_required("admin", "doctor")
def delete_prescription(request, pk):
    presc = get_object_or_404(Prescription, pk=pk)
    if request.method == "POST":
        presc.delete()
        return redirect('prescription-list')
    return render(request, "pharmacie/confirm_delete.html", {"objet": presc, "type": "prescription"})


@role_required("pharmacist", "admin")
def dispensation_detail(request, pk):
    dispensation = get_object_or_404(
        Dispensation.objects.select_related('prescription__patient', 'pharmacien')
        .prefetch_related('items__medication', 'items__lot', 'mouvements'),
        pk=pk,
    )
    return render(request, "pharmacie/dispensation_detail.html", {
        "dispensation": dispensation,
    })


@role_required("admin", "doctor")
def prescription_create_form(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    if request.method == "POST":
        form = PrescriptionForm(request.POST, instance=prescription)
        if form.is_valid():
            form.save()
            return redirect('prescription-detail', pk=prescription.id)
    else:
        form = PrescriptionForm(instance=prescription)
    return render(request, "pharmacie/prescription_form.html", {
        "form":         form,
        "prescription": prescription,
    })


@role_required("pharmacist", "admin")
def dispenser(request, prescription_id):
    """Dispense une prescription — POST uniquement pour éviter les double-clics GET."""
    prescription = get_object_or_404(Prescription, id=prescription_id)
    if request.method != "POST":
        # Page de confirmation avant dispensation
        ruptures = check_stock_disponible(prescription)
        return render(request, "pharmacie/dispensation_confirm.html", {
            "prescription": prescription,
            "ruptures":     ruptures,
        })

    dispensation, erreur = deliver_prescription_service(prescription, request.user)
    if erreur:
        messages.error(request, erreur)
        return redirect('prescription-detail', pk=prescription_id)

    log_action(
        request.user,
        "DELIVER_MEDICINE",
        f"Médicament délivré pour {dispensation.prescription.patient.nom}",
        "PHARMACIE",
    )
    messages.success(request, "Dispensation enregistrée avec succès.")
    return redirect('dispensation-detail', pk=dispensation.pk)


@login_required
def dispensation_pdf(request, pk):
    user = request.user
    role = getattr(user, 'role', None)
    if role not in ('admin', 'pharmacist', 'patient'):
        raise PermissionDenied
    dispensation = get_object_or_404(
        Dispensation.objects.select_related('prescription__patient', 'prescription__medecin')
        .prefetch_related('items__medication'),
        pk=pk,
    )
    if role == 'patient':
        patient_user = getattr(dispensation.prescription.patient, 'compte_patient', None)
        if patient_user is None or patient_user.pk != user.pk:
            raise PermissionDenied
    prescription = dispensation.prescription
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="dispensation_{pk}.pdf"'
    p = canvas.Canvas(response)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(180, 800, "REÇU DE DISPENSATION")
    p.setFont("Helvetica", 12)
    p.drawString(50, 760, f"Patient : {prescription.patient.nom} {prescription.patient.prenom}")
    medecin = prescription.medecin.get_full_name() if prescription.medecin else "N/A"
    p.drawString(50, 740, f"Médecin : {medecin}")
    p.drawString(50, 720, f"Date de dispensation : {dispensation.date:%d/%m/%Y à %H:%M}")
    if dispensation.periode:
        p.drawString(50, 700, f"Période : {dispensation.periode:%m/%Y}")
    y = 670
    p.drawString(50, y, "Médicaments délivrés :")
    y -= 20
    for item in dispensation.items.all():
        lot_info = f" (lot {item.lot.numero_lot})" if item.lot else ""
        p.drawString(60, y, f"- {item.medication.nom}{lot_info} | Qté: {item.quantite}")
        y -= 20
    p.showPage()
    p.save()
    return response

import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.timezone import now

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.utils import log_action
from .models import Appointment
from .forms import AppointmentForm
from .services import create_suivi_after_appointment
from .serializers import (AppointmentReadSerializer,AppointmentWriteSerializer,AppointmentStatutSerializer,)
from users.permissions import IsDoctorOrNurseOrAdmin, IsDoctorOrAdmin
from users.decorators import role_required

# ============================================================
# API
# ============================================================
class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all()

    def get_permissions(self):
        # Lecture : doctor, nurse, admin
        # Écriture : doctor et admin uniquement
        if self.action in ('list', 'retrieve', 'mes_rdv', 'aujourd_hui'):
            return [IsDoctorOrNurseOrAdmin()]
        return [IsDoctorOrAdmin()]

    def perform_create(self, serializer):
        appointment = serializer.save(created_by=self.request.user)
        log_action(
            self.request.user,
            "CREATE_APPOINTMENT",
            f"Rendez-vous créé pour {appointment.patient}",
            "RendezVous",
        )

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AppointmentWriteSerializer
        if self.action == 'changer_statut':
            return AppointmentStatutSerializer
        return AppointmentReadSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Appointment.objects.none()

        qs = Appointment.objects.select_related('patient', 'doctor', 'created_by')
        role = getattr(user, "role", None)

        if role == 'patient':
            return qs.filter(patient__compte_patient=user)
        if role == 'doctor':
            return qs.filter(doctor=user)
        return qs

    @action(detail=False, methods=['get'], url_path='mes-rdv')
    def mes_rdv(self, request):
        qs = self.get_queryset().filter(status='planifie')
        serializer = AppointmentReadSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='aujourd-hui')
    def aujourd_hui(self, request):
        qs = self.get_queryset().filter(date=now().date(), status='planifie')
        serializer = AppointmentReadSerializer(qs, many=True)
        return Response(serializer.data)


# ============================================================
# HTML
# ============================================================
@role_required("admin", "doctor", "nurse")
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    return render(request, 'appointments/appointment_detail.html', {'appointment': appointment})


@role_required("admin", "doctor")
def appointment_delete(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appointment.delete()
        messages.success(request, "Rendez-vous supprimé.")
        return redirect('appointment-list')
    return render(request, 'appointments/appointment_confirm_delete.html', {'appointment': appointment})


@role_required("admin", "doctor")
def appointment_create(request):
    if request.method == "POST":
        form = AppointmentForm(request.POST)
        if form.is_valid():
            rdv = form.save(commit=False)
            rdv.created_by = request.user
            rdv.save()
            messages.success(request, "Rendez-vous créé.")
            return redirect('appointment-list')
    else:
        form = AppointmentForm()

    return render(request, "appointments/appointment_form.html", {"form": form})


@role_required("admin", "doctor", "nurse")
def appointment_list(request):
    role = getattr(request.user, "role", None)

    qs = Appointment.objects.select_related('patient', 'doctor')
    if role == 'patient':
        qs = qs.filter(patient__compte_patient=request.user)
    elif role == 'doctor':
        qs = qs.filter(doctor=request.user)

    patient = request.GET.get('patient')
    doctor = request.GET.get('doctor')
    status = request.GET.get('status')
    date = request.GET.get('date')

    if patient:
        qs = qs.filter(patient__id=patient)
    if doctor:
        qs = qs.filter(doctor__id=doctor)
    if status:
        qs = qs.filter(status=status)
    if date:
        qs = qs.filter(date=date)

    return render(request, 'appointments/appointment_list.html', {'appointments': qs})


@role_required("admin", "doctor", "nurse")
def appointment_calendar(request):
    role = getattr(request.user, "role", None)

    appointments = Appointment.objects.all()
    if role == 'patient':
        appointments = appointments.filter(patient__compte_patient=request.user)
    elif role == 'doctor':
        appointments = appointments.filter(doctor=request.user)

    events = []
    for a in appointments:
        color = "#ffc107"
        if a.status == "effectue":
            color = "#198754"
        elif a.status == "annule":
            color = "#dc3545"

        events.append({
            "title": f"{a.patient} ({a.get_status_display()})",
            "start": f"{a.date}T{a.heure}",
            "color": color,
        })

    return render(request, "appointments/calendar.html", {
        "events": events,
        "events_json": json.dumps(events),
    })


@login_required
def mes_rendez_vous(request):
    if getattr(request.user, "role", None) != "patient":
        return redirect("dashboard")
    return render(request, "appointments/patient_calendar.html")


@login_required
def patient_events(request):
    rdvs = Appointment.objects.filter(patient__compte_patient=request.user)
    events = []
    for r in rdvs:
        color = "#ffc107"
        if r.status == "effectue":
            color = "#198754"
        elif r.status == "annule":
            color = "#dc3545"

        events.append({
            "title": f"RDV - {r.patient.nom}",
            "start": f"{r.date}T{r.heure}",
            "color": color,
            "extendedProps": {
                "medecin": str(r.doctor),
                "motif": r.motif or "Consultation",
                "statut": r.get_status_display(),
            },
        })
    return JsonResponse(events, safe=False)


@role_required("admin", "doctor")
def appointment_update(request, pk):
    rdv = get_object_or_404(Appointment, pk=pk)

    if request.method == "POST":
        old_status = rdv.status
        form = AppointmentForm(request.POST, instance=rdv)
        if form.is_valid():
            rdv = form.save()
            if rdv.status == "effectue" and old_status != "effectue":
                create_suivi_after_appointment(rdv)
            messages.success(request, "Rendez-vous mis à jour.")
            return redirect('appointment-list')
    else:
        form = AppointmentForm(instance=rdv)

    return render(request, "appointments/appointment_form.html", {"form": form})

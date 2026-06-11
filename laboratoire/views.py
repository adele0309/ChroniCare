import json
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.utils import log_action
from .models import LabTest
from .serializers import LabTestSerializer
from .forms import LabTestCreateForm, LabTestResultForm, LabTestInterpretForm
from .services import (
    compute_status,
    trigger_lab_alerts,
    update_suivi_from_labtest,
    notify_prescripteur_result_ready,
    TYPE_TEST_DEFAULTS,
)
from users.permissions import IsDoctorOrLabOrAdmin, IsDoctorOrAdmin, IsLabOrAdmin
from users.decorators import role_required


# ═══════════════════════════════════════════════════════════════
# API ViewSet
# ═══════════════════════════════════════════════════════════════

class LabTestViewSet(viewsets.ModelViewSet):
    queryset = LabTest.objects.all()
    serializer_class = LabTestSerializer

    def get_permissions(self):
        # Création : médecin ou admin uniquement — le lab ne crée jamais
        if self.action == 'create':
            return [IsDoctorOrAdmin()]
        # Modification et suppression : médecin ou admin uniquement
        if self.action in ('update', 'partial_update', 'destroy'):
            return [IsDoctorOrAdmin()]
        # Validation : lab ou admin uniquement — pas le médecin
        if self.action == 'valider':
            return [IsLabOrAdmin()]
        # Lecture et actions spéciales : doctor, lab, admin
        return [IsDoctorOrLabOrAdmin()]

    def get_queryset(self):
        qs = LabTest.objects.select_related(
            'patient', 'technicien', 'validated_by',
            'prescripteur', 'suivi', 'maladie',
        )
        user = self.request.user
        role = getattr(user, 'role', None)

        if role == 'patient':
            # Le patient ne voit que ses propres résultats validés
            return qs.filter(patient__compte_patient=user, is_validated=True)
        if role == 'lab':
            return qs
        if role == 'doctor':
            return qs.filter(prescripteur=user)

        patient_id = self.request.query_params.get('patient')
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs

    def perform_create(self, serializer):
        suivi = serializer.validated_data.get('suivi')
        patient = serializer.validated_data.get('patient')

        # Cohérence patient ↔ suivi
        if suivi and patient and suivi.patient != patient:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "Le patient de l'analyse ne correspond pas au patient du suivi médical."
            )

        labtest = serializer.save(prescripteur=self.request.user)
        log_action(
            self.request.user,
            "CREATE_ANALYSE",
            f"Analyse {labtest.get_type_test_display()} prescrite pour {labtest.patient.nom}",
            "LABORATOIRE",
        )

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        """Réservé au laboratoire — valide un résultat et notifie le médecin."""
        test = self.get_object()
        if test.is_validated:
            return Response(
                {'detail': 'Cette analyse est déjà validée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        test.is_validated = True
        test.validated_by = request.user
        test.validated_at = timezone.now()
        test.save()
        # Mise à jour automatique du suivi médical
        update_suivi_from_labtest(test)
        notify_prescripteur_result_ready(test)
        return Response(self.get_serializer(test).data)

    @action(detail=False, methods=['get'])
    def anomalies(self, request):
        qs = self.get_queryset().filter(status__in=['anormal', 'critique'])
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=['get'])
    def en_attente(self, request):
        qs = self.get_queryset().filter(status='en_attente')
        return Response(self.get_serializer(qs, many=True).data)


# ═══════════════════════════════════════════════════════════════
# HTML views
# ═══════════════════════════════════════════════════════════════

@role_required("admin", "doctor", "lab")
def labtest_list(request):
    role  = getattr(request.user, 'role', None)
    tests = LabTest.objects.select_related(
        'patient', 'technicien', 'prescripteur', 'suivi', 'maladie'
    ).order_by('-urgence', '-date_test')

    if role == 'lab':
        tests = tests.order_by('-urgence', 'status', '-date_test')
    elif role == 'doctor':
        tests = tests.filter(prescripteur=request.user)

    patient_nom = request.GET.get('patient', '').strip()
    status_f    = request.GET.get('status', '').strip()
    date_filter = request.GET.get('date', '').strip()

    if patient_nom:
        from django.db.models import Q
        tests = tests.filter(
            Q(patient__nom__icontains=patient_nom) |
            Q(patient__prenom__icontains=patient_nom)
        )
    if status_f:
        tests = tests.filter(status=status_f)
    if date_filter:
        try:
            tests = tests.filter(date_test__date=date_filter)
        except Exception:
            pass

    return render(request, 'laboratoire/labtest_list.html', {
        'labtests':       tests,
        'status_choices': LabTest.STATUS_CHOICES,
        'page_title':     'Analyses de laboratoire',
        'role':           role,
    })


@role_required("admin", "doctor", "lab")
def labtest_detail(request, pk):
    test = get_object_or_404(
        LabTest.objects.select_related(
            'patient', 'technicien', 'validated_by',
            'prescripteur', 'suivi', 'maladie',
        ),
        pk=pk,
    )
    return render(request, 'laboratoire/labtest_detail.html', {
        'test':       test,
        'page_title': f"{test.get_type_test_display()} — {test.patient.nom}",
    })


@role_required("admin", "doctor")
def labtest_create_from_suivi(request, suivi_pk):
    """Point d'entrée exclusif : médecin prescrit une analyse depuis un suivi."""
    from suivi_medical.models import SuiviMedical
    suivi = get_object_or_404(
        SuiviMedical.objects.select_related('patient', 'medecin'),
        pk=suivi_pk,
    )
    form = LabTestCreateForm(request.POST or None, suivi=suivi)
    if form.is_valid():
        labtest              = form.save(commit=False)
        labtest.suivi        = suivi
        labtest.patient      = suivi.patient
        labtest.prescripteur = request.user
        labtest.status       = 'en_attente'

        defaults = TYPE_TEST_DEFAULTS.get(labtest.type_test, {})
        if labtest.seuil_min is None and defaults.get('seuil_min') is not None:
            labtest.seuil_min = defaults['seuil_min']
        if labtest.seuil_max is None and defaults.get('seuil_max') is not None:
            labtest.seuil_max = defaults['seuil_max']
        if not labtest.unite and defaults.get('unite'):
            labtest.unite = defaults['unite']
        labtest.save()

        log_action(
            request.user,
            "CREATE_ANALYSE",
            f"Analyse {labtest.get_type_test_display()} prescrite pour {suivi.patient.nom}",
            "LABORATOIRE",
        )
        messages.success(
            request,
            f"Demande '{labtest.get_type_test_display()}' envoyée au laboratoire.",
        )
        return redirect('suivi-detail', pk=suivi_pk)

    return render(request, 'laboratoire/labtest_create_from_suivi.html', {
        'form':               form,
        'suivi':              suivi,
        'type_defaults_json': json.dumps(TYPE_TEST_DEFAULTS),
        'page_title':         f"Prescrire une analyse — {suivi.patient.nom} {suivi.patient.prenom}",
    })


@role_required("admin", "lab")
def labtest_result(request, pk):
    """Technicien saisit le résultat d'une analyse en attente."""
    test = get_object_or_404(LabTest, pk=pk)
    form = LabTestResultForm(request.POST or None, instance=test)
    if form.is_valid():
        labtest            = form.save(commit=False)
        labtest.technicien = request.user
        labtest.status     = compute_status(labtest)
        labtest.save()
        trigger_lab_alerts(labtest)
        messages.success(request, "Résultat enregistré.")
        return redirect('labtest-detail', pk=pk)
    return render(request, 'laboratoire/labtest_result.html', {
        'test':       test,
        'form':       form,
        'page_title': f"Saisir résultat — {test.get_type_test_display()}",
    })


@role_required("admin", "lab")
def labtest_validate(request, pk):
    """Technicien valide définitivement le résultat."""
    test = get_object_or_404(LabTest, pk=pk)
    if test.is_validated:
        messages.warning(request, "Cette analyse est déjà validée.")
        return redirect('labtest-detail', pk=pk)
    if request.method == 'POST':
        test.is_validated = True
        test.validated_by = request.user
        test.validated_at = timezone.now()
        test.save()
        update_suivi_from_labtest(test)
        notify_prescripteur_result_ready(test)
        log_action(
            request.user,
            "VALIDATE_ANALYSE",
            f"Analyse {test.get_type_test_display()} validée pour {test.patient.nom}",
            "LABORATOIRE",
        )
        messages.success(request, "Analyse validée. Le médecin prescripteur a été notifié.")
        return redirect('labtest-detail', pk=pk)
    return render(request, 'laboratoire/labtest_validate_confirm.html', {
        'test':       test,
        'page_title': "Valider l'analyse",
    })


@role_required("admin", "doctor")
def labtest_mark_interpreted(request, pk):
    """Médecin interprète le résultat et met à jour le suivi médical."""
    test = get_object_or_404(
        LabTest.objects.select_related('patient', 'suivi', 'prescripteur'),
        pk=pk,
    )
    if not test.is_validated:
        messages.error(request, "Impossible d'interpréter une analyse non encore validée par le laboratoire.")
        return redirect('labtest-detail', pk=pk)
    form = LabTestInterpretForm(request.POST or None, instance=test)
    if form.is_valid():
        labtest                = form.save(commit=False)
        labtest.lu_par_medecin = True
        labtest.date_lecture   = timezone.now()
        labtest.save()
        messages.success(request, "Interprétation enregistrée dans le dossier du patient.")
        return redirect('labtest-detail', pk=pk)
    return render(request, 'laboratoire/labtest_interpret.html', {
        'test':       test,
        'form':       form,
        'page_title': f"Interpréter — {test.get_type_test_display()}",
    })

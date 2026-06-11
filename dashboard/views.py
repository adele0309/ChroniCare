from datetime import date
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from alertes_notifications.models import Alert
from maladies.models import Maladie
from appointments.models import Appointment
from laboratoire.models import LabTest
from patients.models import Patient
from pharmacie.models import Dispensation, Medication, Prescription
from suivi_medical.models import SuiviMedical
from users.decorators import role_required
from users.models import User


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mois_labels(n=6):
    """Returns list of (year, month, label_str) for the last n months (oldest first)."""
    today = date.today()
    result = []
    MOIS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun',
            'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
    for i in range(n - 1, -1, -1):
        total = today.year * 12 + today.month - 1 - i
        year = total // 12
        month = total % 12 + 1
        result.append((year, month, f"{MOIS[month - 1]} {year}"))
    return result


# ── Router ───────────────────────────────────────────────────────────────────

@login_required
def dashboard_page(request):
    role_map = {
        'admin':      'admin-dashboard',
        'doctor':     'medecin-dashboard',
        'nurse':      'infirmier-dashboard',
        'patient':    'patient-dashboard',
        'pharmacist': 'pharmacien-dashboard',
        'lab':        'laboratoire-dashboard',
    }
    target = role_map.get(getattr(request.user, 'role', None))
    return redirect(target) if target else redirect('home')


# ── Admin dashboard ───────────────────────────────────────────────────────────

@role_required('admin')
def admin_dashboard(request):
    months_info = _mois_labels(6)
    oldest_year, oldest_month, _ = months_info[0]
    date_start = date(oldest_year, oldest_month, 1)

    # Monthly consultations
    consult_raw = (
        SuiviMedical.objects
        .filter(created_at__date__gte=date_start)
        .annotate(mois=TruncMonth('created_at'))
        .values('mois')
        .annotate(total=Count('id'))
        .order_by('mois')
    )
    consult_map = {(r['mois'].year, r['mois'].month): r['total'] for r in consult_raw}

    # Monthly new patient users
    patient_raw = (
        User.objects.filter(role='patient', date_joined__date__gte=date_start)
        .annotate(mois=TruncMonth('date_joined'))
        .values('mois')
        .annotate(total=Count('id'))
        .order_by('mois')
    )
    patient_map = {(r['mois'].year, r['mois'].month): r['total'] for r in patient_raw}

    chart_labels   = [m[2] for m in months_info]
    chart_consults = [consult_map.get((m[0], m[1]), 0) for m in months_info]
    chart_patients = [patient_map.get((m[0], m[1]), 0) for m in months_info]

    # User role distribution
    role_labels = ['Médecins', 'Infirmiers', 'Patients', 'Pharmaciens', 'Labo', 'Admins']
    role_values = [
        User.objects.filter(role='doctor').count(),
        User.objects.filter(role='nurse').count(),
        User.objects.filter(role='patient').count(),
        User.objects.filter(role='pharmacist').count(),
        User.objects.filter(role='lab').count(),
        User.objects.filter(role='admin').count(),
    ]

    # Alert distribution
    alerts_critiques = Alert.objects.filter(alert_type='critical', is_resolved=False).count()
    alerts_warnings  = Alert.objects.filter(alert_type='warning',  is_resolved=False).count()
    alerts_info      = Alert.objects.filter(alert_type='info',     is_resolved=False).count()
    alerts_resolues  = Alert.objects.filter(is_resolved=True).count()

    context = {
        'page_title': "Tableau de bord Administrateur",
        # KPIs
        'maladies_count':      Maladie.objects.count(),
        'total_users':         User.objects.count(),
        'doctors':             role_values[0],
        'nurses':              role_values[1],
        'patients':            role_values[2],
        'pharmacists':         role_values[3],
        'labs':                role_values[4],
        'patients_count':      Patient.objects.count(),
        'consultations_count': SuiviMedical.objects.count(),
        'appointments_count':  Appointment.objects.count(),
        'alerts_count':        alerts_critiques + alerts_warnings + alerts_info,
        'recent_users':        User.objects.order_by('-date_joined')[:6],
        # Chart.js — trend line
        'chart_labels':    json.dumps(chart_labels),
        'chart_consults':  json.dumps(chart_consults),
        'chart_patients':  json.dumps(chart_patients),
        # Chart.js — doughnut rôles
        'chart_role_labels': json.dumps(role_labels),
        'chart_role_data':   json.dumps(role_values),
        # Chart.js — alertes bar
        'chart_alert_data': json.dumps([alerts_critiques, alerts_warnings,
                                        alerts_info, alerts_resolues]),
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


# ── Médecin dashboard ─────────────────────────────────────────────────────────

@role_required('doctor')
def medecin_dashboard(request):
    my_suivis = SuiviMedical.objects.filter(medecin=request.user)

    # Vital signs evolution — last 20 consultations with at least one measurement
    raw_suivis = list(
        my_suivis
        .select_related('patient')
        .order_by('created_at')
        .values(
            'created_at',
            'glycemie', 'tension_systolique', 'tension_diastolique',
            'hemoglobine', 'poids',
        )
    )
    vitals_list = [
        s for s in raw_suivis
        if any(s[k] is not None for k in
               ['glycemie', 'tension_systolique', 'tension_diastolique', 'hemoglobine'])
    ][-20:]

    # Monthly consultations trend (last 6 months)
    months_info = _mois_labels(6)
    oldest_year, oldest_month, _ = months_info[0]
    date_start = date(oldest_year, oldest_month, 1)
    consult_raw = (
        my_suivis
        .filter(created_at__date__gte=date_start)
        .annotate(mois=TruncMonth('created_at'))
        .values('mois')
        .annotate(total=Count('id'))
        .order_by('mois')
    )
    consult_map = {(r['mois'].year, r['mois'].month): r['total'] for r in consult_raw}
    chart_labels   = [m[2] for m in months_info]
    chart_consults = [consult_map.get((m[0], m[1]), 0) for m in months_info]

    # Critical unresolved alerts
    critical_alerts = (
        Alert.objects
        .filter(alert_type='critical', is_resolved=False)
        .select_related('patient')
        .order_by('-created_at')[:5]
    )

    context = {
        'page_title': "Tableau de bord Médecin",
        'my_appointments_count': Appointment.objects.filter(doctor=request.user).count(),
        'my_consultations':      my_suivis.count(),
        'patients_count':        Patient.objects.count(),
        'alerts_count':          Alert.objects.filter(is_resolved=False).count(),
        'today_appointments':    Appointment.objects.filter(
                                     doctor=request.user,
                                     date__gte=date.today(),
                                 ).exclude(status='annule').order_by('date', 'heure')[:8],
        'critical_alerts':       critical_alerts,
        # Chart.js — constantes vitales (Python lists, rendered via json_script in template)
        'vitals_labels':    [s['created_at'].strftime('%d/%m/%y') for s in vitals_list],
        'vitals_glycemie':  [s['glycemie']            for s in vitals_list],
        'vitals_tension_s': [s['tension_systolique']  for s in vitals_list],
        'vitals_tension_d': [s['tension_diastolique'] for s in vitals_list],
        'vitals_hemo':      [s['hemoglobine']         for s in vitals_list],
        # Chart.js — tendance mensuelle
        'chart_labels':   chart_labels,
        'chart_consults': chart_consults,
    }
    return render(request, 'dashboard/medecin_dashboard.html', context)


# ── Infirmier dashboard ───────────────────────────────────────────────────────

@role_required('nurse')
def infirmier_dashboard(request):
    context = {
        'page_title': "Tableau de bord Infirmier",
        'patients_count':     Patient.objects.count(),
        'appointments_count': Appointment.objects.count(),
        'alerts_count':       Alert.objects.filter(is_resolved=False).count(),
        'recent_alerts':      Alert.objects.filter(is_resolved=False)
                                  .select_related('patient').order_by('-created_at')[:6],
    }
    return render(request, 'dashboard/infirmier_dashboard.html', context)


# ── Patient dashboard ─────────────────────────────────────────────────────────

@role_required('patient')
def patient_dashboard(request):
    profil    = None
    my_appts  = Appointment.objects.none()
    my_alerts = Alert.objects.none()
    try:
        profil    = request.user.profil_patient
        my_appts  = Appointment.objects.filter(patient=profil).order_by('-id')[:5]
        my_alerts = Alert.objects.filter(patient=profil).order_by('-id')[:5]
    except Patient.DoesNotExist:
        pass
    return render(request, 'dashboard/patient_dashboard.html', {
        'page_title':      "Mon espace",
        'profil':          profil,
        'my_appointments': my_appts,
        'my_alerts':       my_alerts,
    })


# ── Pharmacien dashboard ──────────────────────────────────────────────────────

@role_required('pharmacist')
def pharmacien_dashboard(request):
    all_medications = list(Medication.objects.prefetch_related('lots').all())
    stock_critique  = [m for m in all_medications if m.stock_total <= m.stock_minimum]
    context = {
        'page_title': "Tableau de bord Pharmacien",
        'prescriptions_count':      Prescription.objects.filter(statut='en_attente').count(),
        'medications_count':         len(all_medications),
        'dispensations_count':       Dispensation.objects.count(),
        'stock_critique_count':      len(stock_critique),
        'prescriptions_en_attente':  Prescription.objects.filter(statut='en_attente')
                                         .select_related('patient', 'medecin').order_by('-date')[:10],
        'dispensations_recentes':    Dispensation.objects.select_related(
                                         'prescription__patient', 'pharmacien').order_by('-date')[:5],
        'stock_critique':            stock_critique[:5],
    }
    return render(request, 'dashboard/pharmacien_dashboard.html', context)


# ── Laboratoire dashboard ─────────────────────────────────────────────────────

@role_required('lab')
def laboratoire_dashboard(request):
    context = {
        'page_title': "Tableau de bord Laboratoire",
        'analyses_en_attente': LabTest.objects.filter(status='en_attente').count(),
        'analyses_a_valider':  LabTest.objects.filter(is_validated=False)
                                   .exclude(status='en_attente').count(),
        'anomalies_count':     LabTest.objects.filter(is_abnormal=True).count(),
        'analyses_recentes':   LabTest.objects.select_related('patient', 'technicien')
                                   .order_by('-date_test')[:8],
    }
    return render(request, 'dashboard/laboratoire_dashboard.html', context)


# ── JSON API — constantes vitales par patient ─────────────────────────────────

@role_required('admin', 'doctor')
def api_vitals_evolution(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    qs = SuiviMedical.objects.filter(patient=patient)
    if request.user.role == 'doctor':
        qs = qs.filter(medecin=request.user)
    suivis = list(
        qs.order_by('created_at')
        .values('created_at', 'glycemie', 'tension_systolique',
                'tension_diastolique', 'hemoglobine', 'poids', 'cholesterol')
    )
    return JsonResponse({
        'patient':             str(patient),
        'labels':              [s['created_at'].strftime('%d/%m/%Y') for s in suivis],
        'glycemie':            [s['glycemie'] for s in suivis],
        'tension_systolique':  [s['tension_systolique'] for s in suivis],
        'tension_diastolique': [s['tension_diastolique'] for s in suivis],
        'hemoglobine':         [s['hemoglobine'] for s in suivis],
        'poids':               [s['poids'] for s in suivis],
        'cholesterol':         [s['cholesterol'] for s in suivis],
    })


# ── Export PDF ────────────────────────────────────────────────────────────────

@role_required('admin')
def export_dashboard_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    TEAL       = colors.HexColor('#085041')
    TEAL_LIGHT = colors.HexColor('#E1F5EE')
    GREY       = colors.HexColor('#CCCCCC')
    WHITE      = colors.white

    def make_table(data):
        style_cmds = [
            ('BACKGROUND',   (0, 0), (-1, 0), TEAL),
            ('TEXTCOLOR',    (0, 0), (-1, 0), WHITE),
            ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE',     (0, 0), (-1, -1), 10),
            ('GRID',         (0, 0), (-1, -1), 0.5, GREY),
            ('LEFTPADDING',  (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING',   (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), TEAL_LIGHT))
        t = Table(data, colWidths=[10 * cm, 5 * cm])
        t.setStyle(TableStyle(style_cmds))
        return t

    today_str = date.today().strftime('%Y-%m-%d')
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="rapport_chronicare_{today_str}.pdf"'

    doc = SimpleDocTemplate(
        response, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'cc_title', parent=styles['Title'],
        fontSize=20, textColor=TEAL, spaceAfter=4,
    )
    h2_style = ParagraphStyle(
        'cc_h2', parent=styles['Heading2'],
        fontSize=13, textColor=TEAL, spaceBefore=14, spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        'cc_sub', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#717D7E'),
    )

    elements = [
        Paragraph('Rapport Statistique — ChroniCare', title_style),
        Paragraph(f'Généré le {date.today().strftime("%d/%m/%Y")}', sub_style),
        Spacer(1, 0.6 * cm),

        Paragraph('Indicateurs clés', h2_style),
        make_table([
            ['Indicateur', 'Valeur'],
            ['Patients enregistrés',               str(Patient.objects.count())],
            ['Consultations (suivis médicaux)',     str(SuiviMedical.objects.count())],
            ['Rendez-vous totaux',                  str(Appointment.objects.count())],
            ['Alertes actives (non résolues)',       str(Alert.objects.filter(is_resolved=False).count())],
            ['Alertes critiques non résolues',       str(Alert.objects.filter(alert_type='critical', is_resolved=False).count())],
            ['Prescriptions en attente',            str(Prescription.objects.filter(statut='en_attente').count())],
            ['Analyses de laboratoire (total)',     str(LabTest.objects.count())],
            ['Analyses anormales',                  str(LabTest.objects.filter(is_abnormal=True).count())],
            ['Total utilisateurs',                  str(User.objects.count())],
        ]),

        Spacer(1, 0.4 * cm),
        Paragraph('Répartition du personnel', h2_style),
        make_table([
            ['Rôle', 'Nombre'],
            ['Médecins',       str(User.objects.filter(role='doctor').count())],
            ['Infirmiers',     str(User.objects.filter(role='nurse').count())],
            ['Pharmaciens',    str(User.objects.filter(role='pharmacist').count())],
            ['Laboratoire',    str(User.objects.filter(role='lab').count())],
            ['Administrateurs',str(User.objects.filter(role='admin').count())],
        ]),

        Spacer(1, 0.4 * cm),
        Paragraph('Tendance des consultations (6 derniers mois)', h2_style),
    ]

    months_info = _mois_labels(6)
    oldest_year, oldest_month, _ = months_info[0]
    consult_raw = (
        SuiviMedical.objects
        .filter(created_at__date__gte=date(oldest_year, oldest_month, 1))
        .annotate(mois=TruncMonth('created_at'))
        .values('mois')
        .annotate(total=Count('id'))
        .order_by('mois')
    )
    consult_map = {(r['mois'].year, r['mois'].month): r['total'] for r in consult_raw}
    trend_data = [['Mois', 'Consultations']]
    for year, month, label in months_info:
        trend_data.append([label, str(consult_map.get((year, month), 0))])
    elements.append(make_table(trend_data))

    doc.build(elements)
    return response

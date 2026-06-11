from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Alert, Notification, MessageTemplate
from .serializers import AlertSerializer, NotificationSerializer, MessageTemplateSerializer
from .services import mark_notification_as_read, mark_all_read, resolve_alert, acknowledge_alert
from users.permissions import IsDoctorOrNurseOrAdmin, IsAdmin
from users.decorators import role_required


# ════════════════════════════════════════════════════════════
# API ViewSets
# ════════════════════════════════════════════════════════════

class AlertViewSet(viewsets.ModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [IsDoctorOrNurseOrAdmin]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        qs = Alert.objects.select_related(
            'patient', 'acknowledged_by', 'resolved_by',
            'source_suivi', 'source_labtest',
        )
        # Un médecin/infirmier voit toutes les alertes non résolues en priorité
        # (hôpital : pas de cloisonnement strict par patient)
        if role in ('doctor', 'nurse'):
            alert_type = self.request.query_params.get('alert_type')
            source     = self.request.query_params.get('source')
            resolved   = self.request.query_params.get('resolved')
            if alert_type:
                qs = qs.filter(alert_type=alert_type)
            if source:
                qs = qs.filter(source=source)
            if resolved == 'false':
                qs = qs.filter(is_resolved=False)
            elif resolved == 'true':
                qs = qs.filter(is_resolved=True)
            return qs
        # Admin : accès complet + filtres
        if role == 'admin':
            patient_id = self.request.query_params.get('patient')
            if patient_id:
                qs = qs.filter(patient_id=patient_id)
            return qs
        return Alert.objects.none()

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        alert = self.get_object()
        if alert.is_resolved:
            return Response({'detail': 'Alerte déjà résolue.'}, status=status.HTTP_400_BAD_REQUEST)
        resolve_alert(alert, user=request.user)
        return Response({'detail': 'Alerte résolue.'})

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        if alert.is_acknowledged:
            return Response({'detail': 'Alerte déjà accusée.'}, status=status.HTTP_400_BAD_REQUEST)
        acknowledge_alert(alert, user=request.user)
        return Response({'detail': 'Alerte accusée de réception.'})


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Chaque utilisateur ne voit QUE ses propres notifications
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    def get_object(self):
        # Sécurité supplémentaire : on ne peut accéder qu'à ses propres notifs
        obj = get_object_or_404(Notification, pk=self.kwargs['pk'], user=self.request.user)
        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        mark_notification_as_read(notif)
        return Response({'detail': 'Notification lue.'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        mark_all_read(request.user)
        return Response({'detail': 'Toutes les notifications marquées comme lues.'})


class MessageTemplateViewSet(viewsets.ModelViewSet):
    queryset = MessageTemplate.objects.all()
    serializer_class = MessageTemplateSerializer
    permission_classes = [IsAdmin]


# ════════════════════════════════════════════════════════════
# HTML views
# ════════════════════════════════════════════════════════════

@role_required('admin', 'doctor', 'nurse')
def monitoring_dashboard(request):
    alertes_critiques   = Alert.objects.filter(alert_type='critical', is_resolved=False).count()
    alertes_non_accusees = Alert.objects.filter(
        alert_type='critical', is_resolved=False, acknowledged_by__isnull=True
    ).count()
    alertes_total       = Alert.objects.filter(is_resolved=False).count()
    alertes_recentes    = Alert.objects.filter(is_resolved=False).select_related('patient')[:8]
    notifs_recentes     = Notification.objects.filter(
        user=request.user, is_read=False
    ).order_by('-created_at')[:8]
    nb_notifs_non_lues  = Notification.objects.filter(user=request.user, is_read=False).count()

    return render(request, 'alertes_notifications/monitoring_dashboard.html', {
        'alertes_critiques':    alertes_critiques,
        'alertes_non_accusees': alertes_non_accusees,
        'alertes_total':        alertes_total,
        'alertes_recentes':     alertes_recentes,
        'notifs_recentes':      notifs_recentes,
        'nb_notifs_non_lues':   nb_notifs_non_lues,
    })


@role_required('admin', 'doctor', 'nurse')
def alert_list(request):
    qs = Alert.objects.select_related('patient', 'acknowledged_by', 'resolved_by')

    # Filtres GET
    alert_type = request.GET.get('type')
    source     = request.GET.get('source')
    resolved   = request.GET.get('resolved', 'false')

    if alert_type:
        qs = qs.filter(alert_type=alert_type)
    if source:
        qs = qs.filter(source=source)
    if resolved == 'false':
        qs = qs.filter(is_resolved=False)
    elif resolved == 'true':
        qs = qs.filter(is_resolved=True)

    return render(request, 'alertes_notifications/alert_list.html', {
        'alertes':      qs,
        'alert_types':  Alert.ALERT_TYPE_CHOICES,
        'sources':      Alert.SOURCE_CHOICES,
        'filtre_type':  alert_type,
        'filtre_source': source,
        'filtre_resolved': resolved,
    })


@role_required('admin', 'doctor', 'nurse')
def alert_detail(request, pk):
    alert = get_object_or_404(
        Alert.objects.select_related(
            'patient', 'acknowledged_by', 'resolved_by',
            'source_suivi', 'source_labtest',
        ),
        pk=pk,
    )
    return render(request, 'alertes_notifications/alert_detail.html', {'alert': alert})


@require_POST
@role_required('admin', 'doctor', 'nurse')
def alert_resolve_html(request, pk):
    alert = get_object_or_404(Alert, pk=pk)
    if not alert.is_resolved:
        resolve_alert(alert, user=request.user)
        messages.success(request, 'Alerte marquée comme résolue.')
    else:
        messages.info(request, 'Cette alerte était déjà résolue.')
    return redirect('alert-detail', pk=pk)


@require_POST
@role_required('admin', 'doctor', 'nurse')
def alert_acknowledge_html(request, pk):
    alert = get_object_or_404(Alert, pk=pk)
    if not alert.is_acknowledged:
        acknowledge_alert(alert, user=request.user)
        messages.success(request, 'Accusé de réception enregistré.')
    else:
        messages.info(request, 'Alerte déjà accusée.')
    return redirect('alert-detail', pk=pk)


@login_required
def notification_list(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
    non_lues = notifs.filter(is_read=False).count()
    return render(request, 'alertes_notifications/notification_list.html', {
        'notifications': notifs,
        'non_lues':      non_lues,
    })


@login_required
def notification_detail(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notif.is_read:
        mark_notification_as_read(notif)
    return render(request, 'alertes_notifications/notification_detail.html', {'notif': notif})


@require_POST
@login_required
def notification_mark_all_read(request):
    mark_all_read(request.user)
    messages.success(request, 'Toutes les notifications ont été marquées comme lues.')
    return redirect('notification-list')


@role_required('admin')
def template_page(request):
    templates = MessageTemplate.objects.all().order_by('type', 'title')
    return render(request, 'alertes_notifications/template_list.html', {'templates': templates})


@role_required('admin')
def template_create(request):
    if request.method == 'POST':
        title   = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        ttype   = request.POST.get('type', 'info')
        code    = request.POST.get('code', '').strip() or None
        if not title or not content:
            messages.error(request, 'Le titre et le contenu sont obligatoires.')
        else:
            MessageTemplate.objects.create(title=title, content=content, type=ttype, code=code)
            messages.success(request, f'Template « {title} » créé.')
            return redirect('template-page')
    return render(request, 'alertes_notifications/template_form.html', {
        'type_choices': MessageTemplate.TYPE_CHOICES,
    })


@require_POST
@role_required('admin')
def template_delete(request, pk):
    template = get_object_or_404(MessageTemplate, pk=pk)
    template.delete()
    messages.success(request, 'Modèle supprimé.')
    return redirect('template-page')


# API légère pour le badge de notification dans la sidebar (utilisée en JS)
@login_required
def notification_count_api(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})


from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SuiviMedicalViewSet
from . import views

router = DefaultRouter()
router.register(r'suivis', SuiviMedicalViewSet, basename='suivi')

urlpatterns = [

    # DRF API
    path('', include(router.urls)),

    # HTML VIEWS
    path('list/', views.suivi_list, name='suivi-list'),
    path('create/', views.suivi_create, name='suivi-create'),

    path('<int:pk>/', views.suivi_detail, name='suivi-detail'),
    path('<int:pk>/edit/', views.suivi_update, name='suivi-update'),
    path('<int:pk>/delete/', views.suivi_delete, name='suivi-delete'),
    path('creer/<int:pk>/', views.creer_prescription, name='creer-prescription'),
    path('from-rdv/<int:rdv_id>/', views.create_suivi_from_rdv_view, name='suivi-create-from-rdv'),
]
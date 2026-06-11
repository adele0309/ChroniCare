import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ChroniCare.settings')

app = Celery('ChroniCare')

app.config_from_object('django.conf:settings', namespace='CELERY')

# Découvre automatiquement les tasks.py dans chaque app INSTALLED_APPS
app.autodiscover_tasks()


# ── Task de healthcheck ──────────────────────────────────────────────────────
@app.task(name='ChroniCare.ping')
def ping():
    """Test de bout-en-bout : doit renvoyer 'pong' une fois exécutée par un worker."""
    return 'pong'


# ── Planification Beat ────────────────────────────────────────────────────────
app.conf.beat_schedule = {

    # ── Rappels RDV — chaque heure (ex: 09:00, 10:00 …)
    'rappels-rdv': {
        'task': 'alertes_notifications.envoyer_rappels_rdv',
        'schedule': crontab(minute=0),
    },

    # ── Renouvellements de traitement — chaque jour à 08:00
    'verifier-renouvellements': {
        'task': 'alertes_notifications.verifier_renouvellements',
        'schedule': crontab(minute=0, hour=8),
    },

    # ── Stock médicaments critique — chaque jour à 07:00
    'notifier-stock-critique': {
        'task': 'alertes_notifications.notifier_stock_critique',
        'schedule': crontab(minute=0, hour=7),
    },

    # ── Escalade alertes critiques non accusées — toutes les 2 heures
    'escalader-alertes-critiques': {
        'task': 'alertes_notifications.escalader_alertes_critiques',
        'schedule': crontab(minute=0, hour='*/2'),
    },
}

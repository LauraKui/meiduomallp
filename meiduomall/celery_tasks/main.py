from celery import Celery
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "meiduomall.settings.dev")

celery_app = Celery('meiduo')

celery_app.config_from_object('celery_tasks.config')

celery_app.autodiscover_tasks(['celery_tasks.sms', 'celery_tasks.email'])
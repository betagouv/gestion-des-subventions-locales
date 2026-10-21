# This configuration file is taken from the official Celery documentation:
# http://docs.celeryproject.org/en/stable/django/first-steps-with-django.html
# Please refer to it for additional information.

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gsl.settings")

app = Celery("gsl")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Niveaux de priorité des tâches Celery (Redis: plus le nombre est bas, plus la
# tâche est servie tôt). La priorité par défaut de la file est définie dans les
# settings via CELERY_TASK_DEFAULT_PRIORITY (= TASK_PRIORITY_NORMAL).
TASK_PRIORITY_HIGH = 0
TASK_PRIORITY_NORMAL = 5
TASK_PRIORITY_LOW = 9
# Au-delà de ce nombre d'éléments, un dispatch est considéré "de masse" → priorité basse
TASK_BULK_DISPATCH_THRESHOLD = 10


def priority_for_dispatch_count(count):
    """Priorité haute pour un petit lot interactif (< seuil), basse au-delà."""
    return (
        TASK_PRIORITY_HIGH
        if count < TASK_BULK_DISPATCH_THRESHOLD
        else TASK_PRIORITY_LOW
    )

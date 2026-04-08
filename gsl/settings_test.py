# settings_test.py
from .settings import *  # noqa

DEBUG = False
LOGIN_URL = "/comptes/login/"

GENERATE_DOCUMENT_SIZE = False

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

BYPASS_ANTIVIRUS = True

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

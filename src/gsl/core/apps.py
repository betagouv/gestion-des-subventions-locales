from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class GslcoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gsl.core"
    label = "gsl_core"
    verbose_name = "1. Socle"

    def ready(self):
        import gsl.core.signals  # noqa F401

        autodiscover_modules("bulk_actions")

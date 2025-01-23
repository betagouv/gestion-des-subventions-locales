from django.apps import AppConfig


class GslProjetConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gsl_projet"

    verbose_name = "3. Projets"

    def ready(self):
        import gsl_projet.signals  # noqa F401

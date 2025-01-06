from django.apps import AppConfig


class GslDemarchesSimplifieesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gsl_demarches_simplifiees"

    verbose_name = "2. Démarches Simplifiées"

    def ready(self):
        import gsl_demarches_simplifiees.signals  # noqa F401

from django.apps import AppConfig


class GslProjetConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gsl.projet"
    label = "gsl_projet"

    verbose_name = "3. Projets"

    def ready(self):
        from . import fragments  # noqa: F401

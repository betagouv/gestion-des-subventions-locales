from django.apps import AppConfig


class GslNotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gsl.notification"
    label = "gsl_notification"

    verbose_name = "6. Notification"

    def ready(self):
        import gsl.notification.fragments  # noqa: F401
        import gsl.notification.signals  # noqa F401

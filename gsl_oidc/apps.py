import logging

from django.apps import AppConfig

security_logger = logging.getLogger("gsl.security")


class GslOidcConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gsl_oidc"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out

        user_logged_in.connect(_on_login)
        user_logged_out.connect(_on_logout)


def _on_login(sender, request, user, **kwargs):
    security_logger.info(
        "security_event=login_success user_id=%s ip=%s",
        user.pk,
        request.META.get("REMOTE_ADDR"),
    )


def _on_logout(sender, request, user, **kwargs):
    security_logger.info(
        "security_event=logout user_id=%s ip=%s",
        getattr(user, "pk", "anonymous"),
        request.META.get("REMOTE_ADDR"),
    )

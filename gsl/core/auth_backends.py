from datetime import timedelta
from logging import getLogger

from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

logger = getLogger(__name__)


class LastLoginDeactivationMixin:
    """
    Mixin that deactivates users whose last_login is older than a threshold.
    """

    inactive_after_days = 365

    def user_can_authenticate(self, user):
        # Let the parent backend apply its own checks first (is_active, etc.).
        if not super().user_can_authenticate(user):
            return False

        last_login = getattr(user, "last_login", None)
        if not last_login:
            return True

        cutoff = timezone.now() - timedelta(days=self.inactive_after_days)
        if last_login < cutoff:
            user.is_active = False
            user.save(update_fields=["is_active"])
            logger.info(
                "Deactivating user %s due to last_login=%s older than %s days",
                getattr(user, "pk", None),
                last_login,
                self.inactive_after_days,
            )
            return False

        return True


class LastLoginDeactivationBackend(LastLoginDeactivationMixin, ModelBackend):
    """
    Authentication backend that wraps Django's ModelBackend with the
    LastLoginDeactivationMixin.
    """

    pass

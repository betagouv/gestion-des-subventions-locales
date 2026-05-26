from axes.signals import user_locked_out
from django.dispatch import receiver

from gsl_core.admin_alerts import notify_admins


@receiver(user_locked_out)
def alert_on_lockout(sender, request, username, ip_address, **kwargs):
    from gsl_core.models import Collegue

    user_agent = request.META.get("HTTP_USER_AGENT", "?") if request else "?"
    try:
        user = Collegue.objects.get(username=username)
        notify_admins(
            f"Utilisateur bloqué (brute force) : {user.email} ({username})",
            f"Email : {user.email}\nUsername : {username}\nIP : {ip_address}\nUser-Agent : {user_agent}",
        )
    except Collegue.DoesNotExist:
        notify_admins(
            f"Utilisateur bloqué (brute force) : {username}",
            f"Username : {username}\nIP : {ip_address}\nUser-Agent : {user_agent}",
        )

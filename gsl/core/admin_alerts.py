from django.conf import settings
from django.core.mail import send_mail


def notify_admins(subject: str, body: str) -> None:
    """Envoie une alerte aux destinataires configurés. No-op si non configuré."""
    if not settings.ADMIN_ALERT_RECIPIENTS:
        return
    send_mail(
        subject=f"[Turgot {settings.ENV}] {subject}",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=settings.ADMIN_ALERT_RECIPIENTS,
        fail_silently=False,
    )

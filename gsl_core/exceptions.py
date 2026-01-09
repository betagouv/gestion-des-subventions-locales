"""Custom exceptions with user-facing messages for error pages."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404 as DjangoHttp404


class Http404(DjangoHttp404):
    """
    Custom Http404 exception that supports user-facing messages.

    Usage:
        # Default behavior (shows generic message to user):
        raise Http404("Internal message for developers")

        # With user message (shows custom message to user):
        raise Http404("Internal message", user_message="Cette page n'existe plus")
    """

    def __init__(self, *args, user_message=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_message = user_message


class PermissionDenied(DjangoPermissionDenied):
    """
    Custom PermissionDenied exception that supports user-facing messages.

    Usage:
        # Default behavior (shows generic message to user):
        raise PermissionDenied("Internal message for developers")

        # With user message (shows custom message to user):
        raise PermissionDenied(
            "Internal message",
            user_message="Vous devez être administrateur pour accéder à cette page"
        )
    """

    def __init__(self, *args, user_message=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_message = user_message

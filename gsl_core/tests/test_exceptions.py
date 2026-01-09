"""Tests for custom exceptions with user-facing messages."""

from gsl_core.exceptions import Http404, PermissionDenied


def test_http404_with_user_message():
    """Test that Http404 can store a user_message attribute."""
    exc = Http404(
        "Internal developer message", user_message="Message pour l'utilisateur"
    )

    assert str(exc) == "Internal developer message"
    assert exc.user_message == "Message pour l'utilisateur"


def test_http404_without_user_message():
    """Test that Http404 works without user_message (backwards compatible)."""
    exc = Http404("Some internal error")

    assert str(exc) == "Some internal error"
    assert exc.user_message is None


def test_permission_denied_with_user_message():
    """Test that PermissionDenied can store a user_message attribute."""
    exc = PermissionDenied(
        "Internal: missing permission X",
        user_message="Accès réservé aux administrateurs",
    )

    assert str(exc) == "Internal: missing permission X"
    assert exc.user_message == "Accès réservé aux administrateurs"


def test_permission_denied_without_user_message():
    """Test that PermissionDenied works without user_message (backwards compatible)."""
    exc = PermissionDenied("Some internal error")

    assert str(exc) == "Some internal error"
    assert exc.user_message is None

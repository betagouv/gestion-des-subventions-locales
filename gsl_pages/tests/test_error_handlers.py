import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.test import override_settings

from gsl_core.exceptions import Http404, PermissionDenied
from gsl_core.tests.factories import ClientWithLoggedUserFactory, CollegueFactory


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_404_with_default_http404_shows_generic_message():
    """Test that standard Django Http404 shows generic message (no internal details)."""
    user = CollegueFactory()
    client = ClientWithLoggedUserFactory(user)

    # Simulate what happens with get_object_or_404
    # (it raises Django's Http404 with internal message)
    response = client.get("/this-does-not-exist/")

    assert response.status_code == 404
    content = response.content.decode()
    # Should show generic message
    assert "Veuillez vérifier l'URL ou retourner à la page d'accueil" in content
    assert "Page non trouvée" in content
    # Should NOT show internal details
    assert "Http404" not in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_404_with_custom_user_message():
    """Test that custom Http404 with user_message displays it to the user."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_404_view

    user = CollegueFactory()
    request = RequestFactory().get("/gone/")
    request.user = user

    # Use our custom Http404 with user_message
    exception = Http404(
        "Internal: Page was deleted", user_message="Cette page a été supprimée"
    )
    response = custom_404_view(request, exception)

    assert response.status_code == 404
    content = response.content.decode()
    # Should show user message
    assert "Cette page a été supprimée" in content
    # Should NOT show internal message
    assert "Internal" not in content
    assert "deleted" not in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_404_page_template_structure():
    """Test that 404 page uses the app template structure."""
    user = CollegueFactory()
    client = ClientWithLoggedUserFactory(user)

    response = client.get("/nonexistent-page/")

    assert response.status_code == 404
    content = response.content.decode()
    # Check for base template elements
    assert "Gestion des Subventions Locales" in content
    assert "fr-alert--error" in content
    assert "Retour à l'accueil" in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_403_with_default_permission_denied_shows_generic_message():
    """Test that standard Django PermissionDenied shows generic message."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_403_view

    user = CollegueFactory()
    request = RequestFactory().get("/forbidden/")
    request.user = user

    # Standard Django PermissionDenied with internal message
    exception = DjangoPermissionDenied("User lacks required permission")
    response = custom_403_view(request, exception)

    assert response.status_code == 403
    content = response.content.decode()
    # Should show generic message
    assert "nous contacter" in content
    # Should NOT show internal details
    assert "lacks required permission" not in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_403_with_custom_user_message():
    """Test that custom PermissionDenied with user_message displays it to the user."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_403_view

    user = CollegueFactory()
    request = RequestFactory().get("/admin-only/")
    request.user = user

    # Use our custom PermissionDenied with user_message
    exception = PermissionDenied(
        "Internal: requires admin role",
        user_message="Vous devez être administrateur pour accéder à cette page",
    )
    response = custom_403_view(request, exception)

    assert response.status_code == 403
    content = response.content.decode()
    # Should show user message
    assert "Vous devez être administrateur" in content
    # Should NOT show internal message
    assert "Internal" not in content
    assert "admin role" not in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_403_page_template_structure():
    """Test that 403 page uses the app template structure."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_403_view

    user = CollegueFactory()
    request = RequestFactory().get("/forbidden/")
    request.user = user

    exception = PermissionDenied("Internal message")
    response = custom_403_view(request, exception)

    assert response.status_code == 403
    content = response.content.decode()
    # Check for base template elements
    assert "Accès interdit" in content
    assert "fr-alert--error" in content
    assert "Retour à l'accueil" in content


@pytest.mark.django_db
def test_404_handler_integration():
    """Test that 404 handler returns 404 status."""
    user = CollegueFactory()
    client = ClientWithLoggedUserFactory(user)

    response = client.get("/this-does-not-exist/")

    assert response.status_code == 404

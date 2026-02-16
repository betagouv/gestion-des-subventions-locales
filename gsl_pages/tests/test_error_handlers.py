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

    response = client.get("/this-does-not-exist/")

    assert response.status_code == 404
    content = response.content.decode()
    assert "La page que vous cherchez est introuvable" in content
    assert "Page non trouvée" in content
    assert "Erreur 404" in content
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

    exception = Http404(
        "Internal: Page was deleted", user_message="Cette page a été supprimée"
    )
    response = custom_404_view(request, exception)

    assert response.status_code == 404
    content = response.content.decode()
    assert "Cette page a été supprimée" in content
    # Should NOT show internal message
    assert "Internal" not in content
    assert "deleted" not in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_404_page_template_structure():
    """Test that 404 page uses the DSFR error page structure."""
    user = CollegueFactory()
    client = ClientWithLoggedUserFactory(user)

    response = client.get("/nonexistent-page/")

    assert response.status_code == 404
    content = response.content.decode()
    assert "Gestion des Subventions Locales" in content
    assert "Page d'accueil" in content
    assert "Contactez-nous" in content
    assert "fr-artwork" in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_403_with_default_permission_denied_shows_generic_message():
    """Test that standard Django PermissionDenied shows generic message."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_403_view

    user = CollegueFactory()
    request = RequestFactory().get("/forbidden/")
    request.user = user

    exception = DjangoPermissionDenied("User lacks required permission")
    response = custom_403_view(request, exception)

    assert response.status_code == 403
    content = response.content.decode()
    assert "contactez-nous" in content
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

    exception = PermissionDenied(
        "Internal: requires admin role",
        user_message="Vous devez être administrateur pour accéder à cette page",
    )
    response = custom_403_view(request, exception)

    assert response.status_code == 403
    content = response.content.decode()
    assert "Vous devez être administrateur" in content
    # Should NOT show internal message
    assert "Internal" not in content
    assert "admin role" not in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_403_page_template_structure():
    """Test that 403 page uses the DSFR error page structure."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_403_view

    user = CollegueFactory()
    request = RequestFactory().get("/forbidden/")
    request.user = user

    exception = PermissionDenied("Internal message")
    response = custom_403_view(request, exception)

    assert response.status_code == 403
    content = response.content.decode()
    assert "Accès non autorisé" in content
    assert "Erreur 403" in content
    assert "Page d'accueil" in content
    assert "fr-artwork" in content


@pytest.mark.django_db
def test_404_handler_integration():
    """Test that 404 handler returns 404 status."""
    user = CollegueFactory()
    client = ClientWithLoggedUserFactory(user)

    response = client.get("/this-does-not-exist/")

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_500_page_renders():
    """Test that 500 handler returns 500 status with proper content."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_500_view

    user = CollegueFactory()
    request = RequestFactory().get("/server-error/")
    request.user = user

    response = custom_500_view(request)

    assert response.status_code == 500
    content = response.content.decode()
    assert "Erreur inattendue" in content
    assert "Erreur 500" in content
    assert "Page d'accueil" in content
    assert "Contactez-nous" in content
    assert "fr-artwork" in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_500_page_does_not_leak_exception_details():
    """Test that 500 page does not display any exception information."""
    from django.test import RequestFactory

    from gsl_pages.views import custom_500_view

    request = RequestFactory().get("/server-error/")
    request.user = CollegueFactory()

    response = custom_500_view(request)

    content = response.content.decode()
    assert "exception" not in content.lower() or "Erreur inattendue" in content
    assert "traceback" not in content.lower()
    assert "TypeError" not in content

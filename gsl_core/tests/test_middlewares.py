from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from gsl_core.middlewares import AdminIPWhitelistMiddleware, CheckPerimeterMiddleware


@pytest.fixture
def req():
    return RequestFactory()


def make_user(is_authenticated=True, is_staff=False, perimetre=None):
    return SimpleNamespace(
        is_authenticated=is_authenticated, is_staff=is_staff, perimetre=perimetre
    )


def get_response(req):
    return HttpResponse("OK")


def test_unauthenticated_passes_through(req):
    request = req.get("/")
    request.user = make_user(is_authenticated=False)

    middleware = CheckPerimeterMiddleware(get_response)
    response = middleware(request)

    assert response.status_code == 200
    assert response.content == b"OK"


@pytest.mark.parametrize("is_staff", [True, False])
def test_authenticated_without_perimeter_redirects(req, is_staff):
    request = req.get("/some/path/")
    request.user = make_user(is_authenticated=True, is_staff=is_staff, perimetre=None)

    middleware = CheckPerimeterMiddleware(get_response)
    response = middleware(request)

    assert response.status_code == 302
    assert response["Location"] == reverse("no-perimeter")


@pytest.mark.parametrize("path", ["/admin/some/", "/oidc/some/", "/__debug__/some/"])
def test_excluded_beginning_paths_allowed(req, path):
    request = req.get(path)
    request.user = make_user(is_authenticated=True, is_staff=False, perimetre=None)

    middleware = CheckPerimeterMiddleware(get_response)
    response = middleware(request)

    assert response.status_code == 200


def test_staff_ds_allowed(req):
    request = req.get("/ds/some/")
    request.user = make_user(is_authenticated=True, is_staff=True, perimetre=None)

    middleware = CheckPerimeterMiddleware(get_response)
    response = middleware(request)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        reverse("login"),
        reverse("logout"),
        reverse("no-perimeter"),
    ],
)
def test_authorized_paths_allowed(req, path):
    request = req.get(path)
    request.user = make_user(is_authenticated=True, is_staff=False, perimetre=None)

    middleware = CheckPerimeterMiddleware(get_response)
    response = middleware(request)

    assert response.status_code == 200


# --- AdminIPWhitelistMiddleware tests ---


class TestAdminIPWhitelistMiddleware:
    def test_allowed_ip_passes_through(self, req, settings):
        settings.ADMIN_ALLOWED_IPS = ["1.2.3.4"]
        request = req.get("/admin/")
        request.META["REMOTE_ADDR"] = "1.2.3.4"

        middleware = AdminIPWhitelistMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 200

    def test_disallowed_ip_returns_403(self, req, settings):
        settings.ADMIN_ALLOWED_IPS = ["1.2.3.4"]
        request = req.get("/admin/")
        request.META["REMOTE_ADDR"] = "9.9.9.9"

        middleware = AdminIPWhitelistMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 403

    def test_non_admin_path_always_passes(self, req, settings):
        settings.ADMIN_ALLOWED_IPS = ["1.2.3.4"]
        request = req.get("/projets/")
        request.META["REMOTE_ADDR"] = "9.9.9.9"

        middleware = AdminIPWhitelistMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 200

    def test_empty_whitelist_blocks_all(self, req, settings):
        settings.ADMIN_ALLOWED_IPS = []
        request = req.get("/admin/")
        request.META["REMOTE_ADDR"] = "9.9.9.9"

        middleware = AdminIPWhitelistMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 403

    def test_x_forwarded_for_is_used(self, req, settings):
        settings.ADMIN_ALLOWED_IPS = ["10.0.0.1"]
        request = req.get("/admin/", HTTP_X_FORWARDED_FOR="10.0.0.1, 192.168.0.1")
        request.META["REMOTE_ADDR"] = "192.168.0.1"

        middleware = AdminIPWhitelistMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 200

    def test_x_forwarded_for_disallowed(self, req, settings):
        settings.ADMIN_ALLOWED_IPS = ["10.0.0.1"]
        request = req.get("/admin/", HTTP_X_FORWARDED_FOR="9.9.9.9, 192.168.0.1")
        request.META["REMOTE_ADDR"] = "10.0.0.1"

        middleware = AdminIPWhitelistMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 403

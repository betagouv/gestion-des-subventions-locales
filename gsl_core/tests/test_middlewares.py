from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from gsl_core.middlewares import CheckPerimeterMiddleware


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
    assert response["Location"] == reverse("no_perimeter")


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
        reverse("no_perimeter"),
        reverse("coming-features"),
    ],
)
def test_authorized_paths_allowed(req, path):
    request = req.get(path)
    request.user = make_user(is_authenticated=True, is_staff=False, perimetre=None)

    middleware = CheckPerimeterMiddleware(get_response)
    response = middleware(request)

    assert response.status_code == 200

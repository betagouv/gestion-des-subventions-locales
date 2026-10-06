import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from gsl.core.campagne import (
    _active,
    active_campagne,
    default_campagne,
    get_campagne,
)
from gsl.core.middlewares import CampagneMiddleware
from gsl.core.tests.factories import ClientWithLoggedUserFactory, CollegueFactory

# -- active campagne --


def test_without_an_active_campagne_the_default_applies():
    assert get_campagne() == default_campagne()


def test_the_context_manager_restores_the_previous_campagne():
    with active_campagne(2024):
        assert get_campagne() == 2024

    assert get_campagne() == default_campagne()


def test_the_context_manager_restores_even_on_a_later_change():
    with active_campagne(2024):
        _active.set(2019)

    assert get_campagne() == default_campagne()


# -- middleware --


def _process(path, view_kwargs, session=None):
    request = RequestFactory().get(path)
    request.session = {} if session is None else session
    middleware = CampagneMiddleware(lambda r: HttpResponse())
    with active_campagne():
        middleware.process_view(request, None, (), view_kwargs)
        campagne = get_campagne()
    return request, campagne


def test_the_url_sets_the_active_campagne_and_is_remembered():
    request, campagne = _process("/projets/liste/2024", {"campagne": 2024})

    assert campagne == 2024
    assert request.session["campagne"] == 2024


def test_a_campagne_less_url_reads_the_remembered_one():
    _, campagne = _process("/notification/", {}, session={"campagne": 2024})

    assert campagne == 2024


def test_a_campagne_less_url_without_memory_falls_back():
    _, campagne = _process("/notification/", {})

    assert campagne == default_campagne()


def test_a_campagne_less_url_does_not_overwrite_the_memory():
    session = {"campagne": 2024}
    _process("/notification/", {}, session=session)

    assert session["campagne"] == 2024


def test_leaving_and_returning_keeps_the_campagne():
    session = {}
    _process("/projets/liste/2024", {"campagne": 2024}, session=session)
    _, campagne = _process("/notification/", {}, session=session)

    assert campagne == 2024


def test_the_campagne_does_not_outlive_the_request():
    middleware = CampagneMiddleware(lambda r: HttpResponse())
    request = RequestFactory().get("/projets/liste/2024")
    request.session = {}

    middleware(request)

    assert get_campagne() == default_campagne()


# -- campagne-less bookmarks --


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, target",
    (
        ("/projets/liste", "/projets/liste/{campagne}"),
        ("/simulation/liste/", "/simulation/liste/{campagne}/"),
        ("/programmation/liste/DETR/", "/programmation/liste/DETR/{campagne}/"),
    ),
)
def test_a_campagne_less_bookmark_redirects_to_the_active_campagne(path, target):
    client = ClientWithLoggedUserFactory(CollegueFactory())

    response = client.get(f"{path}?status=accepted")

    expected = target.format(campagne=default_campagne())
    assert response.status_code == 302
    assert response["Location"] == f"{expected}?status=accepted"

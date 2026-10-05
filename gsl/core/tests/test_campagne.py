import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from gsl.core.campagne import (
    _active,
    active_campagne,
    default_campagne,
    get_campagne,
)
from gsl.core.middlewares import CampagneMiddleware
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
)

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


@pytest.fixture
def client():
    return ClientWithLoggedUserFactory(CollegueFactory())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path, target",
    (
        ("/projets/liste", "/projets/liste/{campagne}"),
        ("/simulation/liste/", "/simulation/liste/{campagne}/"),
        ("/programmation/liste/DETR/", "/programmation/liste/DETR/{campagne}/"),
    ),
)
def test_a_campagne_less_bookmark_redirects_to_the_active_campagne(
    client, path, target
):
    response = client.get(f"{path}?status=accepted")

    expected = target.format(campagne=default_campagne())
    assert response.status_code == 302
    assert response["Location"] == f"{expected}?status=accepted"


# -- changer-campagne --


def changer_campagne_url(campagne, next_url=None):
    url = reverse("changer-campagne", kwargs={"campagne": campagne})
    return f"{url}?next={next_url}" if next_url else url


@pytest.mark.django_db
def test_change_campagne_keeps_the_page_with_the_new_campagne(client):
    next_url = reverse(
        "programmation:programmation-projet-list-dotation",
        kwargs={"dotation": "DETR", "campagne": 2026},
    )
    response = client.get(changer_campagne_url(2027, f"{next_url}?status=valid"))
    assert response.status_code == 302
    assert response.url == reverse(
        "programmation:programmation-projet-list-dotation",
        kwargs={"dotation": "DETR", "campagne": 2027},
    )


@pytest.mark.django_db
def test_change_campagne_on_a_page_without_campagne_stays_on_it(client):
    response = client.get(changer_campagne_url(2027, "/notification/"))
    assert response.status_code == 302
    assert response.url == "/notification/"
    assert client.session["campagne"] == 2027


@pytest.mark.django_db
def test_change_campagne_is_remembered_in_session(client):
    client.get(changer_campagne_url(2027, "/"))
    response = client.get("/projets/liste")
    assert response.url == reverse("projet:list", kwargs={"campagne": 2027})


@pytest.mark.django_db
@pytest.mark.parametrize("next_url", [None, "https://evil.com/projets/liste/2026"])
def test_change_campagne_without_safe_next_goes_to_projet_list(client, next_url):
    response = client.get(changer_campagne_url(2027, next_url))
    assert response.url == reverse("projet:list", kwargs={"campagne": 2027})


@pytest.mark.django_db
def test_change_campagne_refuses_unknown_campagne(client):
    response = client.get(changer_campagne_url(1999, "/"))
    assert response.status_code == 404


@pytest.mark.django_db
def test_main_menu_displays_campagne_selector(client):
    url = reverse("projet:list", kwargs={"campagne": 2027})
    response = client.get(url)
    content = response.content.decode()
    assert "Campagne 2027" in content
    assert changer_campagne_url(2026) in content

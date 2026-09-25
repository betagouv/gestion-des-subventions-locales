import pytest
import responses

from gsl.core.api.fonds_vert import (
    FONDS_VERT_BASE_URL,
    FondsVertClient,
    FondsVertCredentialsMissing,
)

LOGIN_URL = f"{FONDS_VERT_BASE_URL}/fonds_vert/login"
DOSSIERS_URL = f"{FONDS_VERT_BASE_URL}/fonds_vert/v2/dossiers"


@pytest.fixture(autouse=True)
def fonds_vert_credentials(settings):
    """Les vraies valeurs de dev (.env) ne doivent pas influencer ces tests :
    on fixe des identifiants factices par défaut, indépendants de l'environnement."""
    settings.FONDS_VERT_USERNAME = "user"
    settings.FONDS_VERT_PASSWORD = "pass"


def _mock_login(token="token"):
    responses.add(responses.POST, LOGIN_URL, json={"access_token": token})


def test_raises_when_credentials_are_missing(settings):
    settings.FONDS_VERT_USERNAME = ""

    with pytest.raises(FondsVertCredentialsMissing):
        FondsVertClient()


@responses.activate
def test_client_logs_in_at_instantiation_using_settings_credentials():
    _mock_login("abc123")

    client = FondsVertClient()

    assert client.token == "abc123"
    assert responses.calls[0].request.body == "username=user&password=pass"


@responses.activate
def test_iter_dossiers_pages_stops_when_next_page_is_none():
    _mock_login()
    responses.add(
        responses.GET,
        DOSSIERS_URL,
        json={"data": [{"id": 1}, {"id": 2}], "next_page": None},
    )

    client = FondsVertClient()

    assert list(client.iter_dossiers_pages()) == [(1, [{"id": 1}, {"id": 2}])]


@responses.activate
def test_iter_dossiers_pages_follows_next_page():
    _mock_login()
    responses.add(
        responses.GET, DOSSIERS_URL, json={"data": [{"id": 1}], "next_page": 2}
    )
    responses.add(
        responses.GET, DOSSIERS_URL, json={"data": [{"id": 2}], "next_page": None}
    )

    client = FondsVertClient()

    assert list(client.iter_dossiers_pages()) == [
        (1, [{"id": 1}]),
        (2, [{"id": 2}]),
    ]


@responses.activate
def test_iter_dossiers_pages_stops_on_empty_page():
    _mock_login()
    responses.add(responses.GET, DOSSIERS_URL, json={"data": [], "next_page": None})

    client = FondsVertClient()

    assert list(client.iter_dossiers_pages()) == []


@responses.activate
def test_iter_dossiers_pages_starts_at_the_given_page():
    _mock_login()
    responses.add(
        responses.GET, DOSSIERS_URL, json={"data": [{"id": 3}], "next_page": None}
    )

    client = FondsVertClient()
    pages = list(client.iter_dossiers_pages(start_page=3))

    assert pages == [(3, [{"id": 3}])]
    assert responses.calls[1].request.params["page"] == "3"


@responses.activate
def test_iter_dossiers_pages_omits_the_date_filter_by_default():
    _mock_login()
    responses.add(responses.GET, DOSSIERS_URL, json={"data": [], "next_page": None})

    client = FondsVertClient()
    list(client.iter_dossiers_pages())

    assert "date_derniere_modification__gte" not in responses.calls[1].request.params


@responses.activate
def test_iter_dossiers_pages_sends_the_date_filter_as_given():
    _mock_login()
    responses.add(responses.GET, DOSSIERS_URL, json={"data": [], "next_page": None})

    client = FondsVertClient()
    list(client.iter_dossiers_pages(since="2026-09-14T00:00:00.000Z"))

    assert (
        responses.calls[1].request.params["date_derniere_modification__gte"]
        == "2026-09-14T00:00:00.000Z"
    )

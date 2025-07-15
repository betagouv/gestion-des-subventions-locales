from django.urls import reverse


def test_documents_url():
    url = reverse(
        "gsl_notification:documents",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/documents/"


def test_modifier_arrete_url():
    url = reverse(
        "gsl_notification:modifier-arrete",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/modifier-arrete/"


def test_create_arrete_signe_url():
    url = reverse(
        "gsl_notification:create-arrete-signe",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/creer-arrete-signe/"


def test_arrete_download_url():
    url = reverse(
        "gsl_notification:arrete-download",
        kwargs={"arrete_id": 456},
    )
    assert url == "/notification/arrete/456/download/"


def test_arrete_delete_url():
    url = reverse(
        "gsl_notification:delete-arrete",
        kwargs={"arrete_id": 789},
    )
    assert url == "/notification/arrete/789/delete/"


def test_arrete_signe_download_url():
    url = reverse(
        "gsl_notification:arrete-signe-download",
        kwargs={"arrete_signe_id": 789},
    )
    assert url == "/notification/arrete-signe/789/download/"


def test_arrete_signe_delete_url():
    url = reverse(
        "gsl_notification:delete-arrete-signe",
        kwargs={"arrete_signe_id": 789},
    )
    assert url == "/notification/arrete-signe/789/delete/"

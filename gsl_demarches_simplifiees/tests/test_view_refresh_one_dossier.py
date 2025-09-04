from unittest.mock import patch

import pytest
from django.contrib import messages
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
)
from gsl_demarches_simplifiees.exceptions import DsConnectionError, DsServiceException
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db


def test_refresh_one_dossier_nominal_case():
    projet = ProjetFactory()
    dossier = projet.dossier_ds
    collegue = CollegueFactory(perimetre=projet.perimetre)
    url = reverse(
        "ds:refresh-one-dossier", kwargs={"dossier_ds_number": dossier.ds_number}
    )
    client = ClientWithLoggedUserFactory(collegue)

    with patch(
        "gsl_demarches_simplifiees.views.save_one_dossier_from_ds",
        return_value=(messages.SUCCESS, "This is fine"),
    ) as mock_api_call:
        response = client.post(url, {"next": "/next-url"}, follow=False)

    assert response.status_code == 302
    assert "next-url" in response.headers["location"]
    response_messages = messages.get_messages(response.wsgi_request)
    assert len(response_messages)
    first_message = tuple(response_messages)[0]
    assert "This is fine" == first_message.message
    assert first_message.level == messages.SUCCESS
    mock_api_call.assert_called_once()


def test_refresh_one_dossier_non_existing_dossier_gives_404():
    projet = ProjetFactory()
    collegue = CollegueFactory(perimetre=projet.perimetre)
    client = ClientWithLoggedUserFactory(collegue)
    url = reverse(
        "ds:refresh-one-dossier",
        kwargs={"dossier_ds_number": 9999999999},
    )
    with patch(
        "gsl_demarches_simplifiees.views.save_one_dossier_from_ds",
        return_value=(messages.SUCCESS, "This is fine"),
    ) as mock_api_call:
        response = client.post(url, {"next": "/next-url"}, follow=False)

    assert response.status_code == 404
    mock_api_call.assert_not_called()


def test_refresh_one_dossier_invalid_perimeter_gives_404():
    projet = ProjetFactory()
    dossier = projet.dossier_ds
    collegue = CollegueFactory()  # unrelated with projet
    client = ClientWithLoggedUserFactory(collegue)
    url = reverse(
        "ds:refresh-one-dossier", kwargs={"dossier_ds_number": dossier.ds_number}
    )

    with patch(
        "gsl_demarches_simplifiees.views.save_one_dossier_from_ds",
        return_value=(messages.SUCCESS, "This is fine"),
    ) as mock_api_call:
        response = client.post(url, {"next": "/next-url"}, follow=False)

    assert response.status_code == 404
    mock_api_call.assert_not_called()


def test_refresh_data_with_ds_service_exception_is_shown():
    projet = ProjetFactory()
    dossier = projet.dossier_ds
    collegue = CollegueFactory(perimetre=projet.perimetre)
    url = reverse(
        "ds:refresh-one-dossier", kwargs={"dossier_ds_number": dossier.ds_number}
    )
    client = ClientWithLoggedUserFactory(collegue)

    with patch(
        "gsl_demarches_simplifiees.views.save_one_dossier_from_ds",
        side_effect=DsServiceException("Mock DS Service exception"),
    ) as mock_api_call:
        response = client.post(url, {"next": "/next-url"}, follow=False)

    mock_api_call.assert_called_once()
    assert response.status_code == 302
    assert "next-url" in response.headers["location"]
    response_messages = messages.get_messages(response.wsgi_request)
    assert len(response_messages) == 1
    first_message = tuple(response_messages)[0]
    assert "Une erreur s’est produite lors de l’appel" in first_message.message
    assert first_message.level == messages.ERROR


def test_refresh_data_with_ds_connection_error_is_shown():
    projet = ProjetFactory()
    dossier = projet.dossier_ds
    collegue = CollegueFactory(perimetre=projet.perimetre)
    url = reverse(
        "ds:refresh-one-dossier", kwargs={"dossier_ds_number": dossier.ds_number}
    )
    client = ClientWithLoggedUserFactory(collegue)

    with patch(
        "gsl_demarches_simplifiees.views.save_one_dossier_from_ds",
        side_effect=DsConnectionError("Mock DS Connection Error"),
    ) as mock_api_call:
        response = client.post(url, {"next": "/next-url"}, follow=False)

    mock_api_call.assert_called_once()
    assert response.status_code == 302
    assert "next-url" in response.headers["location"]
    response_messages = messages.get_messages(response.wsgi_request)
    assert len(response_messages) == 1
    first_message = tuple(response_messages)[0]
    assert "Une erreur s’est produite lors de l’appel" in first_message.message
    assert first_message.level == messages.ERROR


def test_refresh_data_with_random_exception_is_not_caught():
    projet = ProjetFactory()
    dossier = projet.dossier_ds
    collegue = CollegueFactory(perimetre=projet.perimetre)
    url = reverse(
        "ds:refresh-one-dossier", kwargs={"dossier_ds_number": dossier.ds_number}
    )
    client = ClientWithLoggedUserFactory(collegue)

    with patch(
        "gsl_demarches_simplifiees.views.save_one_dossier_from_ds",
        side_effect=Exception("Oh no"),
    ) as mock_api_call:
        with pytest.raises(Exception):
            client.post(url, {"next": "/next-url"}, follow=False)

    mock_api_call.assert_called_once()

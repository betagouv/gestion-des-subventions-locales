import re
from unittest.mock import patch

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def collegue():
    perimetre = PerimetreDepartementalFactory()
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def client(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def projet(collegue):
    return ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        is_budget_vert=False,
    )


def _url(projet):
    return reverse("fragment:gsl_projet:budget_vert_form", kwargs={"pk": projet.pk})


@patch("gsl_projet.forms.DsService")
def test_patch_budget_vert_saves_and_returns_updated_fragment(
    _mock_ds_service, client, projet
):
    response = client.post(
        _url(projet), {"is_budget_vert": "on"}, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    projet.refresh_from_db()
    assert projet.is_budget_vert is True

    content = response.content.decode()
    assert _url(projet) in content
    assert "Modifications enregistrées" in content
    assert re.search(r'type="submit"\s+disabled\s*>', content)


@patch("gsl_projet.forms.DsService")
def test_patch_budget_vert_non_htmx_returns_400(_mock_ds_service, client, projet):
    response = client.post(_url(projet), {"is_budget_vert": "on"})
    assert response.status_code == 400
    projet.refresh_from_db()
    assert projet.is_budget_vert is False


@patch("gsl_projet.forms.DsService")
def test_patch_budget_vert_ds_error_shown_inline_and_rolled_back(
    mock_ds_service, client, projet
):
    mock_ds_service.return_value.update_annotations.side_effect = DsServiceException(
        "Erreur DN"
    )

    response = client.post(
        _url(projet), {"is_budget_vert": "on"}, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    projet.refresh_from_db()
    assert projet.is_budget_vert is False  # rolled back

    content = response.content.decode()
    assert "Erreur DN" in content
    assert "Modifications enregistrées" not in content
    assert re.search(r'type="submit"\s*>', content)


@patch("gsl_projet.forms.DsService")
def test_patch_budget_vert_out_of_perimeter_returns_404(_mock_ds_service, client):
    other_projet = ProjetFactory(
        dossier_ds__perimetre=PerimetreDepartementalFactory(),
        is_budget_vert=False,
    )
    response = client.post(
        _url(other_projet), {"is_budget_vert": "on"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 404

import pytest
from django.urls import reverse

from gsl_demarches_simplifiees.tests.factories import DemarcheFactory, DossierFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def demarche_with_raw_data():
    return DemarcheFactory(raw_ds_data={"titi": "tata"})


@pytest.fixture
def demarche_without_raw_data():
    return DemarcheFactory(raw_ds_data=None)


def test_admin_can_view_demarche_json(
    admin_client, demarche_with_raw_data, demarche_without_raw_data
):
    response = admin_client.get(
        reverse(
            "ds:view-demarche-json",
            kwargs={"demarche_ds_number": demarche_with_raw_data.ds_number},
        )
    )
    assert response.status_code == 200
    response = admin_client.get(
        reverse(
            "ds:view-demarche-json",
            kwargs={"demarche_ds_number": demarche_without_raw_data.ds_number},
        )
    )
    assert response.status_code == 200


@pytest.fixture
def dossier_with_raw_data():
    return DossierFactory(raw_ds_data={"titi": "tata"})


@pytest.fixture
def dossier_without_raw_data():
    return DossierFactory(raw_ds_data=None)


def test_admin_can_view_dossier_json(
    admin_client, dossier_with_raw_data, dossier_without_raw_data
):
    response = admin_client.get(
        reverse(
            "ds:view-dossier-json",
            kwargs={"dossier_ds_number": dossier_with_raw_data.ds_number},
        )
    )
    assert response.status_code == 200
    response = admin_client.get(
        reverse(
            "ds:view-dossier-json",
            kwargs={"dossier_ds_number": dossier_without_raw_data.ds_number},
        )
    )
    assert response.status_code == 200

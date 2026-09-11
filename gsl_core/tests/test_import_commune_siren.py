import pytest
import responses
from django.core.management import call_command

from gsl_core.management.commands.import_commune_siren import (
    SIREN_INSEE_DATASET_API_URL,
)
from gsl_core.models import Commune
from gsl_core.tests.factories import CommuneFactory

pytestmark = pytest.mark.django_db

CSV_URL = "https://static.data.gouv.fr/resources/.../banatic-sireninsee-last.csv"


def _mock_dataset_and_csv(
    csv_bytes, csv_url=CSV_URL, last_modified="2024-03-07T00:00:00"
):
    responses.add(
        responses.GET,
        SIREN_INSEE_DATASET_API_URL,
        json={
            "resources": [
                {
                    "format": "csv",
                    "url": csv_url,
                    "last_modified": last_modified,
                }
            ]
        },
    )
    responses.add(responses.GET, csv_url, body=csv_bytes)


@responses.activate
def test_associates_siren_to_matching_communes():
    commune = CommuneFactory(insee_code="01001")
    other = CommuneFactory(insee_code="01002")
    csv_text = (
        "Reg_com;dep_com;siren;insee;nom_com\n"
        "84;01;210100012;01001;L'Abergement-Clémenciat\n"
        "84;01;210100020;01002;L'Abergement-de-Varey\n"
    )
    _mock_dataset_and_csv(csv_text.encode("cp1252"))

    call_command("import_commune_siren")

    commune.refresh_from_db()
    other.refresh_from_db()
    assert commune.siren == "210100012"
    assert other.siren == "210100020"


@responses.activate
def test_ignores_insee_codes_not_in_database():
    csv_text = "Reg_com;dep_com;siren;insee;nom_com\n84;01;210100012;99999;Inconnue\n"
    _mock_dataset_and_csv(csv_text.encode("cp1252"))

    call_command("import_commune_siren")

    assert not Commune.objects.filter(siren="210100012").exists()


@responses.activate
def test_skips_rows_missing_siren_or_insee():
    commune = CommuneFactory(insee_code="01001")
    csv_text = (
        "Reg_com;dep_com;siren;insee;nom_com\n"
        "84;01;;01001;Sans siren\n"
        "84;01;210100020;;Sans insee\n"
    )
    _mock_dataset_and_csv(csv_text.encode("cp1252"))

    call_command("import_commune_siren")

    commune.refresh_from_db()
    assert commune.siren == ""


@responses.activate
def test_picks_the_most_recently_updated_csv_resource_when_several_exist():
    commune = CommuneFactory(insee_code="01001")
    old_url = "https://example.com/old.csv"
    new_url = "https://example.com/new.csv"
    responses.add(
        responses.GET,
        SIREN_INSEE_DATASET_API_URL,
        json={
            "resources": [
                {
                    "format": "csv",
                    "url": old_url,
                    "last_modified": "2020-01-01T00:00:00",
                },
                {
                    "format": "csv",
                    "url": new_url,
                    "last_modified": "2024-03-07T00:00:00",
                },
            ]
        },
    )
    responses.add(
        responses.GET,
        old_url,
        body="Reg_com;dep_com;siren;insee;nom_com\n84;01;000000000;01001;Ancien\n".encode(
            "cp1252"
        ),
    )
    responses.add(
        responses.GET,
        new_url,
        body="Reg_com;dep_com;siren;insee;nom_com\n84;01;210100012;01001;Récent\n".encode(
            "cp1252"
        ),
    )

    call_command("import_commune_siren")

    commune.refresh_from_db()
    assert commune.siren == "210100012"

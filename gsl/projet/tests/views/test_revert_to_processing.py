import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    DossierDataFactory,
    DossierFactory,
)

from ...constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

DS_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "gsl_demarches_simplifiees"
    / "tests"
    / "ds_fixtures"
)


def _full_ds_dossier_data() -> dict:
    with open(DS_FIXTURES_DIR / "dossier_data.json") as handle:
        return json.loads(handle.read())


def _ds_repasser_en_instruction_response(*, date_traitement: str) -> dict:
    return {
        "data": {
            "dossierRepasserEnInstruction": {
                "dossier": {
                    "dateDerniereModification": date_traitement,
                    "state": "en_instruction",
                    "traitements": [
                        {
                            "id": "traitement-1",
                            "dateTraitement": date_traitement,
                            "event": "repasse_en_instruction",
                        }
                    ],
                }
            }
        }
    }


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre):
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def client(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def notified_projet(collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return projet


@pytest.fixture
def non_notified_projet(collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=None,
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        dotation=DOTATION_DETR,
    )
    return projet


def _url(projet):
    return reverse("gsl_projet:revert-to-processing", kwargs={"projet_id": projet.id})


def test_get_modal_returns_confirmation(client, notified_projet):
    response = client.get(_url(notified_projet), headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Repasser le projet en traitement" in response.content.decode()


def test_post_clears_notified_at(client, collegue):
    """Real end-to-end: only the DN network call is faked. DsService's
    repasser_en_instruction and refresh_dossier_from_saved_data both run for
    real — including ProjetService.create_or_update_from_ds_dossier, which is
    what actually clears notified_at once it sees the dossier's DS state is
    no longer treated. notified_at itself is never mocked."""
    dossier = DossierFactory(
        perimetre=collegue.perimetre,
        porteur_de_projet_arrondissement=None,
        porteur_de_projet_departement=collegue.perimetre.departement,
        ds_state=Dossier.STATE_ACCEPTE,
    )
    DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
    projet = ProjetFactory(dossier_ds=dossier, notified_at=timezone.now())
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        dotation=DOTATION_DETR,
        assiette=10_000,
        date_programmation=timezone.now(),
    )

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_repasser_en_instruction",
        return_value=_ds_repasser_en_instruction_response(
            date_traitement=timezone.now().isoformat()
        ),
    ):
        client.post(_url(projet), {}, headers={"HX-Request": "true"})

    projet.refresh_from_db()
    assert projet.notified_at is None


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_calls_ds_repasser_en_instruction(mock_repasser, client, notified_projet):
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_preserves_enveloppe_projet_status(mock_repasser, client, notified_projet):
    enveloppe_projet = notified_projet.enveloppeprojet_set.first()
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.status == ProjetStatus.ACCEPTED


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_preserves_programmation(mock_repasser, client, notified_projet):
    enveloppe_projet = notified_projet.enveloppeprojet_set.first()
    assert enveloppe_projet.is_programmee
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.is_programmee


def test_get_returns_404_for_non_notified_projet(client, non_notified_projet):
    response = client.get(_url(non_notified_projet), headers={"HX-Request": "true"})
    assert response.status_code == 404


def test_get_returns_404_for_out_of_perimeter_projet():
    other_perimetre = PerimetreDepartementalFactory()
    other_collegue = CollegueWithDSProfileFactory(perimetre=other_perimetre)
    projet = ProjetFactory(
        dossier_ds__perimetre=PerimetreDepartementalFactory(),
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(projet=projet, status=ProjetStatus.ACCEPTED)
    client = ClientWithLoggedUserFactory(other_collegue)
    response = client.get(_url(projet), headers={"HX-Request": "true"})
    assert response.status_code == 404


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_double_dotation_post_calls_ds_once(mock_repasser, collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.ACCEPTED, dotation=DOTATION_DETR
    )
    EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.ACCEPTED, dotation=DOTATION_DSIL
    )
    client = ClientWithLoggedUserFactory(collegue)
    client.post(_url(projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()

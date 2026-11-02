import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from dn.sync.models import Dossier, Dotation
from dn.sync.tests.factories import (
    DossierDataFactory,
    DossierFactory,
)
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)

from ...constants import ProjetStatus
from ...models import EnveloppeProjet
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

DS_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "dn"
    / "sync"
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
                    "datePassageEnInstruction": date_traitement,
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
        dotation=Dotation.DETR,
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
        dotation=Dotation.DETR,
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
        ds_state=Dossier.State.ACCEPTE,
    )
    DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
    projet = ProjetFactory(dossier_ds=dossier, notified_at=timezone.now())
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        dotation=Dotation.DETR,
        assiette=10_000,
        date_programmation=timezone.now(),
    )

    with patch(
        "dn.sync.ds_client.DsMutator.dossier_repasser_en_instruction",
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


@pytest.mark.parametrize(
    "statuses, ds_state",
    (
        # Simple dotation
        ({Dotation.DETR: ProjetStatus.ACCEPTED}, Dossier.State.ACCEPTE),
        ({Dotation.DSIL: ProjetStatus.ACCEPTED}, Dossier.State.ACCEPTE),
        ({Dotation.DETR: ProjetStatus.REFUSED}, Dossier.State.REFUSE),
        ({Dotation.DSIL: ProjetStatus.DISMISSED}, Dossier.State.SANS_SUITE),
        # Double dotation
        (
            {
                Dotation.DETR: ProjetStatus.ACCEPTED,
                Dotation.DSIL: ProjetStatus.ACCEPTED,
            },
            Dossier.State.ACCEPTE,
        ),
        (
            {Dotation.DETR: ProjetStatus.ACCEPTED, Dotation.DSIL: ProjetStatus.REFUSED},
            Dossier.State.ACCEPTE,
        ),
        (
            {
                Dotation.DETR: ProjetStatus.DISMISSED,
                Dotation.DSIL: ProjetStatus.ACCEPTED,
            },
            Dossier.State.ACCEPTE,
        ),
        (
            {Dotation.DETR: ProjetStatus.REFUSED, Dotation.DSIL: ProjetStatus.REFUSED},
            Dossier.State.REFUSE,
        ),
        (
            {
                Dotation.DETR: ProjetStatus.REFUSED,
                Dotation.DSIL: ProjetStatus.DISMISSED,
            },
            Dossier.State.SANS_SUITE,
        ),
        (
            {
                Dotation.DETR: ProjetStatus.DISMISSED,
                Dotation.DSIL: ProjetStatus.DISMISSED,
            },
            Dossier.State.SANS_SUITE,
        ),
    ),
)
def test_post_sets_every_enveloppe_projet_back_to_processing(
    client, collegue, statuses, ds_state
):
    """Real end-to-end: only the DN network call is faked, with the payload
    actually requested by the `dossierRepasserEnInstruction` mutation."""
    projet = _notified_projet_with_dn_history(collegue, statuses, ds_state)

    with patch(
        "dn.sync.ds_client.DsMutator.dossier_repasser_en_instruction",
        return_value=_ds_repasser_en_instruction_response(
            date_traitement=timezone.now().isoformat()
        ),
    ):
        client.post(_url(projet), {}, headers={"HX-Request": "true"})

    enveloppe_projets = EnveloppeProjet.objects.filter(projet=projet)
    assert {ep.dotation: ep.status for ep in enveloppe_projets} == {
        dotation: ProjetStatus.PROCESSING for dotation in statuses
    }
    assert not any(ep.is_programmee for ep in enveloppe_projets)


def _notified_projet_with_dn_history(collegue, statuses, ds_state):
    """A projet notified on DN: passed en instruction, then programmed in
    Turgot, then treated (notified) on DN."""
    now = timezone.now()
    date_passage_en_instruction = now - timedelta(days=10)
    date_programmation = now - timedelta(days=5)
    date_traitement = now - timedelta(days=2)

    raw_data = _full_ds_dossier_data()
    raw_data["state"] = ds_state
    raw_data["datePassageEnInstruction"] = date_passage_en_instruction.isoformat()
    raw_data["dateTraitement"] = date_traitement.isoformat()

    dossier = DossierFactory(
        perimetre=collegue.perimetre,
        porteur_de_projet_arrondissement=None,
        porteur_de_projet_departement=collegue.perimetre.departement,
        ds_state=ds_state,
        ds_date_passage_en_instruction=date_passage_en_instruction,
        ds_date_traitement=date_traitement,
    )
    DossierDataFactory(dossier=dossier, raw_data=raw_data)
    projet = ProjetFactory(dossier_ds=dossier, notified_at=date_traitement)
    for dotation, status in statuses.items():
        EnveloppeProjetFactory(
            projet=projet,
            status=status,
            dotation=dotation,
            assiette=10_000,
            date_programmation=date_programmation,
        )
    return projet


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_double_dotation_post_calls_ds_once(mock_repasser, collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.ACCEPTED, dotation=Dotation.DETR
    )
    EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.ACCEPTED, dotation=Dotation.DSIL
    )
    client = ClientWithLoggedUserFactory(collegue)
    client.post(_url(projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()

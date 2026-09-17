from datetime import UTC, datetime

import pytest

from gsl.projet.constants import (
    DS_TRAITEMENT_EVENT_ACCEPTE,
    DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
    DS_TRAITEMENT_EVENT_DEPOSE,
    DS_TRAITEMENT_EVENT_DEPOSE_CORRECTION_INSTRUCTEUR,
    DS_TRAITEMENT_EVENT_DEPOSE_CORRECTION_USAGER,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_REFUSE,
    DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION,
    DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION,
)
from gsl.projet.tests.factories import ProjetFactory
from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory
from gsl_demarches_simplifiees.tests.factories import DossierDataFactory

from ..models import ProjetAction, get_or_create_collegue_from_traitement_email

pytestmark = pytest.mark.django_db


def _dossier_with_traitements(*, traitements):
    projet = ProjetFactory()
    DossierDataFactory(dossier=projet.dossier_ds, raw_data={"traitements": traitements})
    return projet


def _traitement(id, event, date="2025-01-15T10:00:00+00:00", email_agent_traitant=None):
    traitement = {"id": id, "event": event, "dateTraitement": date}
    if email_agent_traitant is not None:
        traitement["emailAgentTraitant"] = email_agent_traitant
    return traitement


@pytest.mark.parametrize(
    "event, action_type",
    [
        (DS_TRAITEMENT_EVENT_DEPOSE, ProjetAction.TYPE_DEPOT_DOSSIER),
        (
            DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
            ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        ),
        (
            DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT,
            ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        ),
        (
            DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION,
            ProjetAction.TYPE_RETOUR_EN_INSTRUCTION,
        ),
        (
            DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION,
            ProjetAction.TYPE_RETOUR_EN_CONSTRUCTION,
        ),
        (DS_TRAITEMENT_EVENT_ACCEPTE, ProjetAction.TYPE_NOTIFIED),
        (DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT, ProjetAction.TYPE_NOTIFIED),
        (DS_TRAITEMENT_EVENT_REFUSE, ProjetAction.TYPE_NOTIFIED),
        (DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT, ProjetAction.TYPE_NOTIFIED),
        (DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE, ProjetAction.TYPE_NOTIFIED),
    ],
)
def test_creates_the_matching_action_type_for_each_known_event(event, action_type):
    projet = _dossier_with_traitements(traitements=[_traitement("traitement-1", event)])

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 1
    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == action_type
    assert action.source == ProjetAction.SOURCE_DN
    assert action.source_id == "traitement-1"
    assert action.created_at == datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "event",
    [
        DS_TRAITEMENT_EVENT_DEPOSE_CORRECTION_USAGER,
        DS_TRAITEMENT_EVENT_DEPOSE_CORRECTION_INSTRUCTEUR,
        "some_unknown_event",
    ],
)
def test_ignores_events_without_a_mapped_action_type(event):
    projet = _dossier_with_traitements(traitements=[_traitement("traitement-1", event)])

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 0
    assert not ProjetAction.objects.filter(projet=projet).exists()


@pytest.mark.parametrize(
    "traitement",
    [
        {"id": "", "event": "depose", "dateTraitement": "2025-01-15T10:00:00+00:00"},
        {"id": "traitement-1", "event": "depose", "dateTraitement": ""},
        {"id": "traitement-1", "event": "depose"},
    ],
)
def test_ignores_traitements_missing_id_or_date(traitement):
    projet = _dossier_with_traitements(traitements=[traitement])

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 0
    assert not ProjetAction.objects.filter(projet=projet).exists()


def test_creates_one_action_per_traitement_in_order():
    projet = _dossier_with_traitements(
        traitements=[
            _traitement(
                "traitement-1", DS_TRAITEMENT_EVENT_DEPOSE, "2025-01-01T00:00:00+00:00"
            ),
            _traitement(
                "traitement-2",
                DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
                "2025-01-02T00:00:00+00:00",
            ),
            _traitement(
                "traitement-3", DS_TRAITEMENT_EVENT_ACCEPTE, "2025-01-03T00:00:00+00:00"
            ),
        ]
    )

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 3
    source_ids = set(
        ProjetAction.objects.filter(projet=projet).values_list("source_id", flat=True)
    )
    assert source_ids == {"traitement-1", "traitement-2", "traitement-3"}


def test_is_idempotent_when_rerun_on_the_same_traitements():
    projet = _dossier_with_traitements(
        traitements=[_traitement("traitement-1", DS_TRAITEMENT_EVENT_DEPOSE)]
    )

    first_created_count = ProjetAction.objects.create_from_dossier_traitements(projet)
    second_created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert first_created_count == 1
    assert second_created_count == 0
    assert ProjetAction.objects.filter(projet=projet).count() == 1


def test_only_creates_actions_for_new_traitements_on_resync():
    projet = _dossier_with_traitements(
        traitements=[_traitement("traitement-1", DS_TRAITEMENT_EVENT_DEPOSE)]
    )
    ProjetAction.objects.create_from_dossier_traitements(projet)

    # Le dossier a avancé depuis : un nouveau traitement DN est apparu.
    projet.dossier_ds.ds_data.raw_data = {
        "traitements": [
            _traitement("traitement-1", DS_TRAITEMENT_EVENT_DEPOSE),
            _traitement("traitement-2", DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION),
        ]
    }
    projet.dossier_ds.ds_data.save()

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 1
    assert ProjetAction.objects.filter(projet=projet).count() == 2
    assert ProjetAction.objects.filter(
        projet=projet,
        action_type=ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        source_id="traitement-2",
    ).exists()


def test_returns_zero_when_dossier_has_no_ds_data():
    projet = ProjetFactory()

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 0
    assert not ProjetAction.objects.filter(projet=projet).exists()


def test_returns_zero_when_dossier_has_no_traitements():
    projet = _dossier_with_traitements(traitements=[])

    created_count = ProjetAction.objects.create_from_dossier_traitements(projet)

    assert created_count == 0


def test_sets_actor_from_traitement_email_agent_traitant():
    projet = _dossier_with_traitements(
        traitements=[
            _traitement(
                "traitement-1",
                DS_TRAITEMENT_EVENT_ACCEPTE,
                email_agent_traitant="Instructeur@Example.Net",
            )
        ]
    )

    ProjetAction.objects.create_from_dossier_traitements(projet)

    action = ProjetAction.objects.get(projet=projet)
    assert action.actor is not None
    assert action.actor.email == "instructeur@example.net"


def test_reuses_existing_collegue_matching_the_traitement_email():
    existing = CollegueFactory(email="instructeur@example.net")
    projet = _dossier_with_traitements(
        traitements=[
            _traitement(
                "traitement-1",
                DS_TRAITEMENT_EVENT_ACCEPTE,
                email_agent_traitant="instructeur@example.net",
            )
        ]
    )

    ProjetAction.objects.create_from_dossier_traitements(projet)

    action = ProjetAction.objects.get(projet=projet)
    assert action.actor == existing


def test_leaves_actor_null_when_traitement_has_no_email_agent_traitant():
    projet = _dossier_with_traitements(
        traitements=[_traitement("traitement-1", DS_TRAITEMENT_EVENT_ACCEPTE)]
    )

    ProjetAction.objects.create_from_dossier_traitements(projet)

    action = ProjetAction.objects.get(projet=projet)
    assert action.actor is None


class TestGetOrCreateCollegueFromTraitementEmail:
    def test_returns_none_for_falsy_traitement(self):
        assert get_or_create_collegue_from_traitement_email(None) is None
        assert get_or_create_collegue_from_traitement_email({}) is None

    def test_returns_none_when_email_agent_traitant_is_missing_or_blank(self):
        assert get_or_create_collegue_from_traitement_email({}) is None
        assert (
            get_or_create_collegue_from_traitement_email({"emailAgentTraitant": "   "})
            is None
        )

    def test_creates_a_collegue_for_a_new_email(self):
        collegue = get_or_create_collegue_from_traitement_email(
            {"emailAgentTraitant": "Instructeur@Example.Net"}
        )

        assert collegue is not None
        assert collegue.email == "instructeur@example.net"
        assert Collegue.objects.count() == 1

    def test_reuses_an_existing_collegue_case_insensitively(self):
        existing = CollegueFactory(email="instructeur@example.net")

        collegue = get_or_create_collegue_from_traitement_email(
            {"emailAgentTraitant": "Instructeur@Example.Net"}
        )

        assert collegue == existing
        assert Collegue.objects.count() == 1

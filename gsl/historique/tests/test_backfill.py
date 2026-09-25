import logging
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from django.core.management import call_command

from gsl.core.tests.factories import PerimetreArrondissementFactory
from gsl.projet.tests.factories import ProjetFactory
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierDataFactory

from ..models import ProjetAction

pytestmark = pytest.mark.django_db

COMMAND = "backfill_projet_action_source_id"
MODULE = "gsl.historique.management.commands.backfill_projet_action_source_id"


def _projet_with_traitements(perimetre, *, date_traitement, traitements=None):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__ds_date_traitement=date_traitement,
        dossier_ds__perimetre=perimetre,
    )
    if traitements is None:
        traitements = [
            {
                "id": "traitement-1",
                "event": "classe_sans_suite",
                "dateTraitement": date_traitement.isoformat(),
                "emailAgentTraitant": "agent@example.fr",
                "motivation": "Motif DN",
            }
        ]
    DossierDataFactory(dossier=projet.dossier_ds, raw_data={"traitements": traitements})
    return projet, traitements


def _notified_action(projet, *, created_at, source_id=""):
    return ProjetAction.objects.create(
        projet=projet,
        action_type=ProjetAction.TYPE_NOTIFIED,
        source=ProjetAction.SOURCE_DN,
        created_at=created_at,
        source_id=source_id,
    )


def _stub_ds_client(mock_ds_client_class, *, traitements):
    """Fait renvoyer à `DsClient().get_one_dossier(...)` les traitements
    donnés, comme si DN les avait retournés tels quels lors du
    rafraîchissement."""
    mock_client = mock_ds_client_class.return_value
    mock_client.get_one_dossier.return_value = {"traitements": traitements}
    return mock_client


@mock.patch(f"{MODULE}.DsClient")
def test_associates_source_id_when_traitement_is_within_tolerance(mock_ds_client_class):
    perimetre = PerimetreArrondissementFactory()
    date_traitement = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    projet, traitements = _projet_with_traitements(
        perimetre, date_traitement=date_traitement
    )
    action = _notified_action(projet, created_at=date_traitement + timedelta(seconds=2))
    mock_client = _stub_ds_client(mock_ds_client_class, traitements=traitements)

    call_command(COMMAND)

    mock_client.get_one_dossier.assert_called_once_with(projet.dossier_ds.ds_number)
    action.refresh_from_db()
    assert action.source_id == "traitement-1"


@mock.patch(f"{MODULE}.DsClient")
def test_picks_the_closest_traitement_among_several_notification_events(
    mock_ds_client_class,
):
    """Among the notification-triggering events (accepte/refuse/classe_sans_suite),
    the match is purely date-based: it loops over all of them and keeps the
    closest one, not just the one whose `event` matches the dossier's current
    state (cf. get_last_traitement_matching_dossier_state, used for live DN syncs but
    not for this backfill)."""
    perimetre = PerimetreArrondissementFactory()
    date_traitement = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    projet, traitements = _projet_with_traitements(
        perimetre,
        date_traitement=date_traitement,
        traitements=[
            {
                "id": "refuse-then-repris",
                "event": "refuse",
                "dateTraitement": "2024-12-01T00:00:00+00:00",
            },
            {
                "id": "classe-sans-suite",
                "event": "classe_sans_suite",
                "dateTraitement": date_traitement.isoformat(),
            },
        ],
    )
    _stub_ds_client(mock_ds_client_class, traitements=traitements)
    # Closest to "refuse-then-repris", even though the dossier's current state
    # (SANS_SUITE) matches the other traitement.
    action = _notified_action(
        projet,
        created_at=datetime(2024, 12, 1, 0, 0, 2, tzinfo=UTC),
    )

    call_command(COMMAND)

    action.refresh_from_db()
    assert action.source_id == "refuse-then-repris"


@mock.patch(f"{MODULE}.DsClient")
def test_ignores_non_notification_events_even_when_closer(mock_ds_client_class):
    """A `depose`/`repasse_en_instruction`/... traitement is never an
    acceptable match, even if it's chronologically closer to the action than
    any accepte/refuse/classe_sans_suite traitement."""
    perimetre = PerimetreArrondissementFactory()
    date_traitement = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    projet, traitements = _projet_with_traitements(
        perimetre,
        date_traitement=date_traitement,
        traitements=[
            {
                "id": "depose",
                "event": "depose",
                "dateTraitement": date_traitement.isoformat(),
            },
            {
                "id": "classe-sans-suite",
                "event": "classe_sans_suite",
                "dateTraitement": (date_traitement + timedelta(seconds=2)).isoformat(),
            },
        ],
    )
    _stub_ds_client(mock_ds_client_class, traitements=traitements)
    action = _notified_action(projet, created_at=date_traitement)

    call_command(COMMAND)

    action.refresh_from_db()
    assert action.source_id == "classe-sans-suite"


@mock.patch(f"{MODULE}.DsClient")
def test_alerts_instead_of_guessing_when_no_traitement_is_close_enough(
    mock_ds_client_class, caplog
):
    perimetre = PerimetreArrondissementFactory()
    date_traitement = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    projet, traitements = _projet_with_traitements(
        perimetre, date_traitement=date_traitement
    )
    _stub_ds_client(mock_ds_client_class, traitements=traitements)
    action = _notified_action(projet, created_at=date_traitement + timedelta(hours=1))

    with caplog.at_level(logging.WARNING):
        call_command(COMMAND)

    assert "correspondance incertaine" in caplog.text
    action.refresh_from_db()
    assert action.source_id == ""


@mock.patch(f"{MODULE}.DsClient")
def test_skips_actions_that_already_have_a_source_id(mock_ds_client_class):
    perimetre = PerimetreArrondissementFactory()
    date_traitement = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    projet, _traitements = _projet_with_traitements(
        perimetre, date_traitement=date_traitement
    )
    _notified_action(projet, created_at=date_traitement, source_id="already-set")

    call_command(COMMAND)

    mock_ds_client_class.return_value.get_one_dossier.assert_not_called()


@mock.patch(f"{MODULE}.DsClient")
def test_logs_and_continues_when_the_dn_refresh_fails(mock_ds_client_class, caplog):
    perimetre = PerimetreArrondissementFactory()
    date_traitement = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    projet, _traitements = _projet_with_traitements(
        perimetre, date_traitement=date_traitement
    )
    action = _notified_action(projet, created_at=date_traitement)
    mock_ds_client_class.return_value.get_one_dossier.side_effect = Exception("boom")

    with caplog.at_level(logging.ERROR):
        call_command(COMMAND)

    assert "échec du rafraîchissement DN" in caplog.text
    action.refresh_from_db()
    assert action.source_id == ""

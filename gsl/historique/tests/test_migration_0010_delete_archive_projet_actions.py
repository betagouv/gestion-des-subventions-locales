import importlib
from datetime import UTC, datetime

import pytest
from django.apps import apps as django_apps

from gsl.historique.models import ProjetAction
from gsl.projet.tests.factories import ProjetFactory


def _action(projet, action_type, day, details=""):
    return ProjetAction.objects.create(
        projet=projet,
        action_type=action_type,
        source=ProjetAction.SOURCE_DN,
        details=details,
        created_at=datetime(2026, 6, day, tzinfo=UTC),
    )


@pytest.mark.django_db
def test_migration_deletes_archive_deactivations_and_following_reactivations():
    mod = importlib.import_module(
        "gsl.historique.migrations.0010_delete_archive_projet_actions"
    )
    projet = ProjetFactory()
    archived = _action(projet, "deactivation", 1, "archive")
    unarchived = _action(projet, "reactivation", 2)
    corbeille = _action(projet, "deactivation", 3, "corbeille")
    restored = _action(projet, "reactivation", 4)
    archived_then_trashed = _action(projet, "deactivation", 5, "archive")
    trashed = _action(projet, "deactivation", 6, "corbeille")
    restored_from_trash = _action(projet, "reactivation", 7)

    other_projet = ProjetFactory()
    other_reactivation = _action(other_projet, "reactivation", 8)

    mod.delete_archive_projet_actions(django_apps, None)

    remaining_ids = set(ProjetAction.objects.values_list("id", flat=True))
    assert remaining_ids == {
        corbeille.id,
        restored.id,
        trashed.id,
        restored_from_trash.id,
        other_reactivation.id,
    }
    assert archived.id not in remaining_ids
    assert unarchived.id not in remaining_ids
    assert archived_then_trashed.id not in remaining_ids

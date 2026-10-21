import importlib

import pytest
from django.apps import apps as django_apps

from dn.sync.models import Dossier
from dn.sync.tests.factories import DossierFactory


@pytest.mark.django_db
def test_migration_reactivates_only_archived_dossiers():
    mod = importlib.import_module(
        "dn.sync.migrations.0060_remove_archive_raison_desactivation"
    )
    archived = DossierFactory(is_active=False, raison_desactivation="archive")
    trashed = DossierFactory(
        is_active=False, raison_desactivation=Dossier.RAISON_DESACTIVATION_CORBEILLE
    )

    mod.reactivate_archived_dossiers(django_apps, None)

    archived.refresh_from_db()
    assert archived.is_active is True
    assert archived.raison_desactivation == ""

    trashed.refresh_from_db()
    assert trashed.is_active is False
    assert trashed.raison_desactivation == Dossier.RAISON_DESACTIVATION_CORBEILLE

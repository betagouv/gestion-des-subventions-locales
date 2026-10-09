import importlib

import pytest
from django.apps import apps as django_apps

from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory


@pytest.mark.django_db
def test_migration_reactivates_only_archived_dossiers():
    mod = importlib.import_module(
        "gsl_demarches_simplifiees.migrations.0060_remove_archive_raison_desactivation"
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

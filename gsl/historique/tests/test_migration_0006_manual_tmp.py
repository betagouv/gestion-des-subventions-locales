import importlib
from datetime import UTC, datetime

import pytest
from django.apps import apps as django_apps

from gsl.historique.models import ProjetAction
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.tests.factories import ProjetFactory


@pytest.mark.django_db
def test_migration_deletes_only_spurious_actions():
    mod = importlib.import_module(
        "gsl.historique.migrations.0006_delete_spurious_retour_en_construction_actions"
    )

    # Spurious: never went to instruction
    d1 = DossierFactory(
        ds_date_passage_en_instruction=None,
        ds_date_passage_en_construction=datetime(2025, 6, 5, tzinfo=UTC),
    )
    p1 = ProjetFactory(dossier_ds=d1)
    a1 = ProjetAction.objects.create(
        projet=p1, action_type="retour_en_construction", source="dn"
    )

    # Spurious: instruction date is after construction date (normal chronology, no real retour)
    d2 = DossierFactory(
        ds_date_passage_en_instruction=datetime(2025, 6, 10, tzinfo=UTC),
        ds_date_passage_en_construction=datetime(2025, 6, 5, tzinfo=UTC),
    )
    p2 = ProjetFactory(dossier_ds=d2)
    a2 = ProjetAction.objects.create(
        projet=p2, action_type="retour_en_construction", source="dn"
    )

    # Real: construction date after instruction date => real retour
    d3 = DossierFactory(
        ds_date_passage_en_instruction=datetime(2025, 6, 1, tzinfo=UTC),
        ds_date_passage_en_construction=datetime(2025, 6, 10, tzinfo=UTC),
    )
    p3 = ProjetFactory(dossier_ds=d3)
    a3 = ProjetAction.objects.create(
        projet=p3, action_type="retour_en_construction", source="dn"
    )

    mod.delete_spurious_retour_en_construction_actions(django_apps, None)

    assert not ProjetAction.objects.filter(pk=a1.pk).exists()
    assert not ProjetAction.objects.filter(pk=a2.pk).exists()
    assert ProjetAction.objects.filter(pk=a3.pk).exists()

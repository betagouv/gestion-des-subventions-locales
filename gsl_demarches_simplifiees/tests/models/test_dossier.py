import pytest

from gsl_demarches_simplifiees.models import DossierData
from gsl_demarches_simplifiees.tests.factories import (
    DossierDataFactory,
    DossierFactory,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "demande_montant, finance_cout_total, expected_taux",
    (
        (None, None, None),
        (None, 1_000, None),
        (1_000, None, None),
        (1_000, 10_000, 10),
        (1_000, 3_000, 33.33),
        (2_000, 3_000, 66.67),
    ),
)
def test_taux_demande(demande_montant, finance_cout_total, expected_taux):
    dossier = DossierFactory(
        demande_montant=demande_montant,
        finance_cout_total=finance_cout_total,
    )
    assert dossier.taux_demande == expected_taux


@pytest.mark.parametrize(
    "annotations_champ_libre_1, annotations_champ_libre_2, annotations_champ_libre_3, expected_has_annotations_champ_libre",
    (
        ("", "", "", False),
        ("", "", "test", True),
        ("", "test", "", True),
        ("", "test", "test", True),
        ("test", "", "", True),
        ("test", "", "test", True),
        ("test", "test", "", True),
        ("test", "test", "test", True),
    ),
)
def test_has_annotations_champ_libre(
    annotations_champ_libre_1,
    annotations_champ_libre_2,
    annotations_champ_libre_3,
    expected_has_annotations_champ_libre,
):
    dossier = DossierFactory(
        annotations_champ_libre_1=annotations_champ_libre_1,
        annotations_champ_libre_2=annotations_champ_libre_2,
        annotations_champ_libre_3=annotations_champ_libre_3,
    )
    assert dossier.has_annotations_champ_libre == expected_has_annotations_champ_libre


def test_deleting_dossier_cascade_deletes_dossier_data():
    """When a Dossier is deleted, the linked DossierData is removed (CASCADE)."""
    dossier = DossierFactory()
    dossier_data = DossierDataFactory(dossier=dossier)
    dossier_data_id = dossier_data.pk
    assert DossierData.objects.filter(pk=dossier_data_id).exists()

    dossier.delete()

    assert not DossierData.objects.filter(pk=dossier_data_id).exists()

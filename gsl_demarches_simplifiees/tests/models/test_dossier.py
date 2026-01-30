import pytest

from gsl_demarches_simplifiees.tests.factories import (
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

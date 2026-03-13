import pytest

from gsl_demarches_simplifiees.models import Dossier, DossierData
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
        (1_000, 3_000, 33.3333),
        (2_000, 3_000, 66.6667),
    ),
)
def test_taux_demande(demande_montant, finance_cout_total, expected_taux):
    dossier = DossierFactory(
        demande_montant=demande_montant,
        finance_cout_total=finance_cout_total,
    )
    if expected_taux is None:
        assert dossier.taux_demande is None
    else:
        assert round(dossier.taux_demande, 4) == expected_taux


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


@pytest.mark.parametrize(
    "ds_state, annotations_dotation, annotations_assiette_detr, annotations_montant_accorde_detr, annotations_assiette_dsil, annotations_montant_accorde_dsil, expected",
    [
        # Non-accepted state → always False
        (Dossier.STATE_EN_INSTRUCTION, "", None, None, None, None, False),
        (Dossier.STATE_REFUSE, "DETR", 100, 50, None, None, False),
        # Accepted but no annotations_dotation → True (missing)
        (Dossier.STATE_ACCEPTE, "", None, None, None, None, True),
        (Dossier.STATE_ACCEPTE, "[]", None, None, None, None, True),
        (Dossier.STATE_ACCEPTE, None, None, None, None, None, True),
        # DETR: missing assiette or montant → True
        (Dossier.STATE_ACCEPTE, "DETR", None, 50, None, None, True),
        (Dossier.STATE_ACCEPTE, "DETR", 100, None, None, None, True),
        (Dossier.STATE_ACCEPTE, "DETR", None, None, None, None, True),
        # DETR: both filled → False
        (Dossier.STATE_ACCEPTE, "DETR", 100, 50, None, None, False),
        # DSIL: missing assiette or montant → True
        (Dossier.STATE_ACCEPTE, "DSIL", None, None, None, 50, True),
        (Dossier.STATE_ACCEPTE, "DSIL", None, None, 100, None, True),
        (Dossier.STATE_ACCEPTE, "DSIL", None, None, None, None, True),
        # DSIL: both filled → False
        (Dossier.STATE_ACCEPTE, "DSIL", None, None, 100, 50, False),
        # DETR, DSIL combined: DETR checked first, so if DETR missing → True
        (Dossier.STATE_ACCEPTE, "DETR, DSIL", None, 50, 100, 50, True),
        # Both dotations complete → False
        (Dossier.STATE_ACCEPTE, "DETR, DSIL", 100, 50, 100, 50, False),
    ],
)
def test_has_missing_annotations(
    ds_state,
    annotations_dotation,
    annotations_assiette_detr,
    annotations_montant_accorde_detr,
    annotations_assiette_dsil,
    annotations_montant_accorde_dsil,
    expected,
):
    dossier = DossierFactory(
        ds_state=ds_state,
        annotations_dotation=annotations_dotation or "",
        annotations_assiette_detr=annotations_assiette_detr,
        annotations_montant_accorde_detr=annotations_montant_accorde_detr,
        annotations_assiette_dsil=annotations_assiette_dsil,
        annotations_montant_accorde_dsil=annotations_montant_accorde_dsil,
    )
    assert dossier.has_missing_annotations == expected


def test_deleting_dossier_cascade_deletes_dossier_data():
    """When a Dossier is deleted, the linked DossierData is removed (CASCADE)."""
    dossier = DossierFactory()
    dossier_data = DossierDataFactory(dossier=dossier)
    dossier_data_id = dossier_data.pk
    assert DossierData.objects.filter(pk=dossier_data_id).exists()

    dossier.delete()

    assert not DossierData.objects.filter(pk=dossier_data_id).exists()

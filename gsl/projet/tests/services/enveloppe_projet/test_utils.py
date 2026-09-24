from datetime import UTC

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import Enveloppe
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

from ....constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ....services.enveloppe_projet_services import (
    EnveloppeProjetService as dps,
)
from ...factories import (
    EnveloppeProjetFactory,
    ProjetFactory,
)


@pytest.fixture
def perimetres():
    arr_dijon = PerimetreArrondissementFactory()
    dep_21 = PerimetreDepartementalFactory(
        departement=arr_dijon.departement, region=arr_dijon.region
    )
    region_bfc = PerimetreRegionalFactory(region=dep_21.region)

    arr_nanterre = PerimetreArrondissementFactory()
    dep_92 = PerimetreDepartementalFactory(departement=arr_nanterre.departement)
    region_idf = PerimetreRegionalFactory(region=dep_92.region)
    return [
        arr_dijon,
        dep_21,
        region_bfc,
        arr_nanterre,
        dep_92,
        region_idf,
    ]


# -- _get_root_enveloppe_from_enveloppe_projet --


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_root_enveloppe_from_enveloppe_projet_with_a_detr_and_arrondissement_projet(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
    )
    dep_detr_enveloppe = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    _arr_detr_enveloppe = DetrEnveloppeFactory(
        perimetre=arr_dijon, annee=2025, parent=dep_detr_enveloppe
    )

    enveloppe = dps._get_root_enveloppe_from_enveloppe_projet(enveloppe_projet)
    assert enveloppe == dep_detr_enveloppe


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_root_enveloppe_from_enveloppe_projet_with_a_dsil_and_region_projet(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
    )
    region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    dep_dsil_enveloppe_delegated = DsilEnveloppeFactory(
        perimetre=dep_21, annee=2025, parent=region_dsil_enveloppe
    )
    _arr_dsil_enveloppe_delegated = DsilEnveloppeFactory(
        perimetre=arr_dijon, annee=2025, parent=dep_dsil_enveloppe_delegated
    )

    enveloppe = dps._get_root_enveloppe_from_enveloppe_projet(enveloppe_projet)

    assert enveloppe == region_dsil_enveloppe


@pytest.mark.django_db
@freeze_time("2026-05-06")
def test_get_enveloppe_from_enveloppe_projet_with_a_next_year_date(perimetres, caplog):
    arr_dijon, _, region_bfc, *_ = perimetres
    region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.ACCEPTED,
        enveloppe=region_dsil_enveloppe,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            2026, 1, 15, tzinfo=UTC
        ),
    )

    with pytest.raises(Enveloppe.DoesNotExist):  # No enveloppe for 2026
        dps._get_root_enveloppe_from_enveloppe_projet(enveloppe_projet)

    record = caplog.records[0]
    assert record.message == "No enveloppe found for a enveloppe projet"
    assert record.levelname == "WARNING"
    assert (
        getattr(record, "dossier_ds_number", None)
        == enveloppe_projet.dossier_ds.ds_number
    )
    assert getattr(record, "dotation", None) == enveloppe_projet.dotation
    assert getattr(record, "year", None) == 2026
    assert getattr(record, "perimetre", None) == arr_dijon


@pytest.mark.django_db
@pytest.mark.parametrize(
    "date_traitement, allow_next_year, expected_annee",
    [
        (timezone.datetime(2025, 10, 1, tzinfo=UTC), False, 2025),
        (timezone.datetime(2025, 11, 1, tzinfo=UTC), False, 2025),
        (timezone.datetime(2026, 10, 1, tzinfo=UTC), False, 2026),
        (timezone.datetime(2026, 11, 1, tzinfo=UTC), False, 2026),
        (timezone.datetime(2025, 10, 1, tzinfo=UTC), True, 2025),
        (timezone.datetime(2025, 11, 1, tzinfo=UTC), True, 2026),
        (timezone.datetime(2026, 10, 1, tzinfo=UTC), True, 2026),
        (timezone.datetime(2026, 11, 1, tzinfo=UTC), True, 2027),
    ],
)
def test_get_enveloppe_from_enveloppe_projet_with_a_date_traitement_after_november(
    perimetres, date_traitement, allow_next_year, expected_annee
):
    arr_dijon, _, region_bfc, *_ = perimetres
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2026)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2027)

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_date_traitement=date_traitement,
    )

    enveloppe = dps._get_root_enveloppe_from_enveloppe_projet(
        enveloppe_projet, allow_next_year=allow_next_year
    )
    assert enveloppe.annee == expected_annee


# -- get_dotations_from_field --


@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "value, expected_dotation",
    [
        ("DETR", [DOTATION_DETR]),
        ("DSIL", [DOTATION_DSIL]),
        ("[DETR, DSIL]", [DOTATION_DETR, DOTATION_DSIL]),
        ("DETR et DSIL", [DOTATION_DETR, DOTATION_DSIL]),
        ("['DETR', 'DSIL', 'DETR et DSIL']", [DOTATION_DETR, DOTATION_DSIL]),
    ],
)
@pytest.mark.django_db
def test_get_dotations_from_field(field, value, expected_dotation):
    projet = ProjetFactory()
    setattr(projet.dossier_ds, field, value)
    dotation = dps._get_dotations_from_field(projet, field)
    assert dotation == expected_dotation


# -- get_assiette_from_dossier --


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_assiette_from_annotations_handles_missing_assiette(caplog):
    """Test _get_assiette_from_annotations handles missing assiette"""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=None,
    )

    assiette_detr = dps._get_assiette_from_annotations(projet.dossier_ds, DOTATION_DETR)
    assert assiette_detr is None

    assiette_dsil = dps._get_assiette_from_annotations(projet.dossier_ds, DOTATION_DSIL)
    assert assiette_dsil is None


# -- get_montant_from_dossier --


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_montant_from_dossier_handles_missing_montant(caplog):
    """Test _get_montant_from_dossier handles missing montant"""
    projet = ProjetFactory(
        dossier_ds__annotations_montant_accorde_detr=None,
        dossier_ds__annotations_montant_accorde_dsil=None,
    )

    montant_detr = dps._get_montant_from_dossier(projet.dossier_ds, DOTATION_DETR)
    assert montant_detr == 0

    montant_dsil = dps._get_montant_from_dossier(projet.dossier_ds, DOTATION_DSIL)
    assert montant_dsil == 0

    # Check that warnings were logged
    assert len(caplog.records) == 2
    assert "Montant is missing" in caplog.records[0].message


# -- _is_programmation_date_after_passage_en_instruction --


@pytest.mark.django_db
def test_is_programmation_date_after_passage_en_instruction_without_programmation():
    """Test _is_programmation_date_after_passage_en_instruction returns False when the dotation isn't programmed"""
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.PROCESSING)

    result = dps._is_programmation_date_after_passage_en_instruction(enveloppe_projet)

    assert result is False


@pytest.mark.django_db
def test_is_programmation_date_after_passage_en_instruction_when_before_passage_en_instruction():
    """Test _is_programmation_date_after_passage_en_instruction returns False when date_programmation is before ds_date_passage_en_instruction"""
    dossier = DossierFactory(
        ds_date_passage_en_instruction=timezone.datetime(2025, 1, 15, tzinfo=UTC)
    )
    projet = ProjetFactory(dossier_ds=dossier)
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        date_programmation=timezone.datetime(2025, 1, 10, tzinfo=UTC),
    )

    result = dps._is_programmation_date_after_passage_en_instruction(enveloppe_projet)

    assert result is False
    assert enveloppe_projet.date_programmation < dossier.ds_date_passage_en_instruction


@pytest.mark.django_db
def test_is_programmation_date_after_passage_en_instruction_when_after_passage_en_instruction():
    """Test _is_programmation_date_after_passage_en_instruction returns True when date_programmation is after ds_date_passage_en_instruction"""
    dossier = DossierFactory(
        ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, 10, 0, 0, tzinfo=UTC
        )
    )
    projet = ProjetFactory(dossier_ds=dossier)
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        date_programmation=timezone.datetime(2025, 1, 20, tzinfo=UTC),
    )

    result = dps._is_programmation_date_after_passage_en_instruction(enveloppe_projet)

    assert result is True
    assert enveloppe_projet.date_programmation > dossier.ds_date_passage_en_instruction


@pytest.mark.django_db
def test_is_programmation_date_after_passage_en_instruction_with_none_date():
    """Test _is_programmation_date_after_passage_en_instruction raises TypeError when ds_date_passage_en_instruction is None"""
    dossier = DossierFactory(ds_date_passage_en_instruction=None)
    projet = ProjetFactory(dossier_ds=dossier)
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        date_programmation=timezone.datetime(2025, 1, 20, tzinfo=UTC),
    )

    # When ds_date_passage_en_instruction is None, the comparison raises TypeError
    with pytest.raises(TypeError, match="not supported between instances of"):
        dps._is_programmation_date_after_passage_en_instruction(enveloppe_projet)

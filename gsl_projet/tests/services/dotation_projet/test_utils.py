from datetime import UTC

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
)
from gsl_projet.services.dotation_projet_services import (
    DotationProjetService as dps,
)
from gsl_projet.tests.factories import (
    DotationProjetFactory,
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


# -- _get_root_enveloppe_from_dotation_projet --


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_root_enveloppe_from_dotation_projet_with_a_detr_and_arrondissement_projet(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__perimetre=arr_dijon,
    )
    dep_detr_enveloppe = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    _arr_detr_enveloppe = DetrEnveloppeFactory(
        perimetre=arr_dijon, annee=2025, deleguee_by=dep_detr_enveloppe
    )

    enveloppe = dps._get_root_enveloppe_from_dotation_projet(dotation_projet)
    assert enveloppe == dep_detr_enveloppe


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_root_enveloppe_from_dotation_projet_with_a_dsil_and_region_projet(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_ACCEPTED,
        projet__perimetre=arr_dijon,
    )
    region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    dep_dsil_enveloppe_delegated = DsilEnveloppeFactory(
        perimetre=dep_21, annee=2025, deleguee_by=region_dsil_enveloppe
    )
    _arr_dsil_enveloppe_delegated = DsilEnveloppeFactory(
        perimetre=arr_dijon, annee=2025, deleguee_by=dep_dsil_enveloppe_delegated
    )

    enveloppe = dps._get_root_enveloppe_from_dotation_projet(dotation_projet)

    assert enveloppe == region_dsil_enveloppe


@pytest.mark.django_db
@freeze_time("2026-05-06")
def test_get_enveloppe_from_dotation_projet_with_a_next_year_date(perimetres, caplog):
    arr_dijon, _, region_bfc, *_ = perimetres
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_ACCEPTED,
        projet__perimetre=arr_dijon,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            2026, 1, 15, tzinfo=UTC
        ),
    )
    _region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    with pytest.raises(Enveloppe.DoesNotExist):  # No enveloppe for 2026
        dps._get_root_enveloppe_from_dotation_projet(dotation_projet)

    record = caplog.records[0]
    assert record.message == "No enveloppe found for a dotation projet"
    assert record.levelname == "WARNING"
    assert (
        getattr(record, "dossier_ds_number", None)
        == dotation_projet.dossier_ds.ds_number
    )
    assert getattr(record, "dotation", None) == dotation_projet.dotation
    assert getattr(record, "year", None) == 2026
    assert getattr(record, "perimetre", None) == arr_dijon


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
def test_get_assiette_from_dossier_handles_missing_assiette(caplog):
    """Test _get_assiette_from_dossier handles missing assiette"""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=None,
    )

    assiette_detr = dps._get_assiette_from_dossier(projet.dossier_ds, DOTATION_DETR)
    assert assiette_detr is None

    assiette_dsil = dps._get_assiette_from_dossier(projet.dossier_ds, DOTATION_DSIL)
    assert assiette_dsil is None

    # Check that warnings were logged
    assert len(caplog.records) == 2
    assert "Assiette is missing" in caplog.records[0].message


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

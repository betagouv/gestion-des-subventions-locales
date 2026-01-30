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
    ProgrammationProjetFactory,
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
        projet__dossier_ds__perimetre=arr_dijon,
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
        projet__dossier_ds__perimetre=arr_dijon,
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
        projet__dossier_ds__perimetre=arr_dijon,
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
def test_get_enveloppe_from_dotation_projet_with_a_date_traitement_after_november(
    perimetres, date_traitement, allow_next_year, expected_annee
):
    arr_dijon, _, region_bfc, *_ = perimetres
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2026)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2027)

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_date_traitement=date_traitement,
    )

    enveloppe = dps._get_root_enveloppe_from_dotation_projet(
        dotation_projet, allow_next_year=allow_next_year
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


# -- _is_programmation_projet_created_after_date_of_passage_en_instruction --


@pytest.mark.django_db
def test_is_programmation_projet_created_after_date_of_passage_en_instruction_without_programmation_projet():
    """Test _is_programmation_projet_created_after_date_of_passage_en_instruction returns False when there's no programmation_projet"""
    dotation_projet = DotationProjetFactory()

    result = dps._is_programmation_projet_created_after_date_of_passage_en_instruction(
        dotation_projet
    )

    assert result is False


@pytest.mark.django_db
def test_is_programmation_projet_created_after_date_of_passage_en_instruction_when_pp_is_created_before_passage_en_instruction():
    """Test _is_programmation_projet_created_after_date_of_passage_en_instruction returns False when programmation_projet.created_at is before ds_date_passage_en_instruction"""
    dossier = DossierFactory(
        ds_date_passage_en_instruction=timezone.datetime(2025, 1, 15, tzinfo=UTC)
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(projet=projet)

    # Create programmation_projet with frozen time (2025-01-10) which is before passage en instruction (2025-01-15)
    with freeze_time("2025-01-10"):
        programmation_projet = ProgrammationProjetFactory(
            dotation_projet=dotation_projet,
        )

    result = dps._is_programmation_projet_created_after_date_of_passage_en_instruction(
        dotation_projet
    )

    assert result is False
    assert programmation_projet.created_at < dossier.ds_date_passage_en_instruction


@pytest.mark.django_db
def test_is_programmation_projet_created_after_date_of_passage_en_instruction_when_pp_is_created_after_passage_en_instruction():
    """Test _is_programmation_projet_created_after_date_of_passage_en_instruction returns True when programmation_projet.created_at is after ds_date_passage_en_instruction"""
    dossier = DossierFactory(
        ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, 10, 0, 0, tzinfo=UTC
        )
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(projet=projet)

    # Create programmation_projet with frozen time (2025-01-20) which is after passage en instruction (2025-01-15)
    with freeze_time("2025-01-20"):
        programmation_projet = ProgrammationProjetFactory(
            dotation_projet=dotation_projet,
        )

    result = dps._is_programmation_projet_created_after_date_of_passage_en_instruction(
        dotation_projet
    )

    assert result is True
    assert programmation_projet.created_at > dossier.ds_date_passage_en_instruction


@pytest.mark.django_db
def test_is_programmation_projet_created_after_date_of_passage_en_instruction_with_none_date():
    """Test _is_programmation_projet_created_after_date_of_passage_en_instruction raises TypeError when ds_date_passage_en_instruction is None"""
    dossier = DossierFactory(ds_date_passage_en_instruction=None)
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(projet=projet)

    # Create programmation_projet with frozen time
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        created_at=timezone.datetime(2025, 1, 20, tzinfo=UTC),
    )

    # When ds_date_passage_en_instruction is None, the comparison raises TypeError
    with pytest.raises(TypeError, match="not supported between instances of"):
        dps._is_programmation_projet_created_after_date_of_passage_en_instruction(
            dotation_projet
        )

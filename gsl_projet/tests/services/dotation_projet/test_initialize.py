import logging
from datetime import UTC

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import (
    DotationProjetService as dps,
)
from gsl_projet.tests.factories import (
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


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_accepted_with_annotations_dotation(
    perimetres,
):
    """Test _initialize_dotation_projets_from_projet_accepted when annotations_dotation is set"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_dotation="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=20_000,
        dossier_ds__annotations_montant_accorde_detr=5_000,
        dossier_ds__annotations_montant_accorde_dsil=15_000,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dotation_projets = dps._initialize_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED
    assert detr_dp.assiette == 10_000
    assert detr_dp.detr_avis_commission is True
    assert detr_dp.montant_retenu == 5_000
    assert detr_dp.taux_retenu == 50

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_ACCEPTED
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.detr_avis_commission is None
    assert dsil_dp.montant_retenu == 15_000
    assert dsil_dp.taux_retenu == 75


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_accepted_with_empty_annotations_dotation_falls_back_to_demande_dispositif_sollicite(
    perimetres, caplog
):
    """Test _initialize_dotation_projets_from_projet_accepted when annotations_dotation is empty, falls back to demande_dispositif_sollicite"""

    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_dotation="",  # Empty
        dossier_ds__demande_dispositif_sollicite="DETR",
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_montant_accorde_detr=None,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    # --

    with caplog.at_level(logging.WARNING):
        dotation_projets = dps._initialize_dotation_projets_from_projet_accepted(projet)

    # --

    assert len(dotation_projets) == 1
    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED
    assert detr_dp.assiette is None, "Assiette should be None if assiette is missing"
    assert detr_dp.montant_retenu == 0, "Montant should be 0 if montant is missing"
    assert detr_dp.taux_retenu == 0, "Taux should be 0 if montant is missing"
    assert detr_dp.detr_avis_commission is True
    assert detr_dp.programmation_projet is not None
    assert detr_dp.programmation_projet.status == PROJET_STATUS_ACCEPTED

    # Check log message, level and extra
    assert len(caplog.records) == 3

    record = caplog.records[0]
    assert (
        record.message
        == "No dotations found in annotations_dotation for accepted dossier during initialisation"
    )
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "projet", None) == projet.pk
    assert getattr(record, "value", None) == ""
    assert getattr(record, "field", None) == "annotations_dotation"

    record = caplog.records[1]
    assert record.message == "Assiette is missing in dossier annotations"
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "dotation", None) == DOTATION_DETR

    record = caplog.records[2]
    assert record.message == "Montant is missing in dossier annotations"
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "dotation", None) == DOTATION_DETR


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_refused(perimetres):
    """Test _initialize_dotation_projets_from_projet_refused"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__demande_dispositif_sollicite="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=None,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dotation_projets = dps._initialize_dotation_projets_from_projet_refused(projet)

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_REFUSED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 0
    assert detr_dp.taux_retenu == 0
    assert detr_dp.detr_avis_commission is None
    assert detr_dp.programmation_projet is not None
    assert detr_dp.programmation_projet.status == PROJET_STATUS_REFUSED

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_REFUSED
    assert dsil_dp.assiette is None
    assert dsil_dp.montant_retenu == 0
    assert dsil_dp.taux_retenu == 0
    assert dsil_dp.detr_avis_commission is None
    assert dsil_dp.programmation_projet is not None
    assert dsil_dp.programmation_projet.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_sans_suite(perimetres):
    """Test _initialize_dotation_projets_from_projet_sans_suite"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__demande_dispositif_sollicite="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=None,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dotation_projets = dps._initialize_dotation_projets_from_projet_sans_suite(projet)

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_DISMISSED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 0
    assert detr_dp.taux_retenu == 0

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_DISMISSED
    assert dsil_dp.assiette is None
    assert dsil_dp.montant_retenu == 0
    assert dsil_dp.taux_retenu == 0


@pytest.mark.django_db
def test_initialize_dotation_projets_from_projet_en_construction_or_instruction():
    """Test _initialize_dotation_projets_from_projet_en_construction_or_instruction"""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=20_000,
    )

    dotation_projets = (
        dps._initialize_dotation_projets_from_projet_en_construction_or_instruction(
            projet
        )
    )

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_PROCESSING
    assert detr_dp.assiette is None
    assert detr_dp.montant_retenu is None
    assert not hasattr(detr_dp, "programmation_projet")

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_PROCESSING
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.montant_retenu is None
    assert not hasattr(dsil_dp, "programmation_projet")

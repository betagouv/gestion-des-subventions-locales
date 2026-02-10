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
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
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


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_accepted_creates_new_dotation_projets(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_accepted creates new dotation projets"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        demande_dispositif_sollicite="DETR",
        annotations_assiette_detr=None,
        annotations_montant_accorde_detr=None,
        ds_date_traitement=None,
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(
        dossier_ds=dossier,
    )

    dps._initialize_dotation_projets_from_projet(projet)
    assert projet.dotationprojet_set.count() == 1

    # Projet has been accepted on DN for DETR and DSIL
    dossier.annotations_dotation = "DETR et DSIL"
    dossier.annotations_assiette_detr = 10_000
    dossier.annotations_montant_accorde_detr = 5_000
    dossier.annotations_assiette_dsil = 20_000
    dossier.annotations_montant_accorde_dsil = 15_000
    dossier.ds_date_traitement = timezone.datetime(2025, 1, 15, tzinfo=UTC)
    dossier.save()

    dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 2
    assert projet.dotationprojet_set.count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 5_000
    assert detr_dp.taux_retenu == 50

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_ACCEPTED
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.montant_retenu == 15_000
    assert dsil_dp.taux_retenu == 75


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "dotation_status",
    (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED),
)
def test_update_dotation_projets_from_projet_accepted_keeps_dotation_projets_if_refused_or_dismissed(
    perimetres,
    dotation_status,
):
    """Test _update_dotation_projets_from_projet_accepted keeps dotation projets not in annotations_dotation if not refused or dismissed"""
    # Arrange
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        demande_dispositif_sollicite="DETR et DSIL",
        ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)

    dps._initialize_dotation_projets_from_projet(projet)
    assert projet.dotationprojet_set.count() == 2

    projet.dotationprojet_set.filter(dotation=DOTATION_DSIL).update(
        status=dotation_status
    )

    # Act
    projet.dossier_ds.annotations_dotation = "DETR"
    projet.dossier_ds.annotations_assiette_detr = 10_000
    projet.dossier_ds.annotations_montant_accorde_detr = 5_000
    projet.dossier_ds.save()

    dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    # Assert
    assert len(dotation_projets) == 2
    assert projet.dotationprojet_set.count() == 2
    assert DotationProjet.objects.filter(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    ).exists()
    assert DotationProjet.objects.filter(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_status
    ).exists()


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "dotation_status",
    (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING),
)
def test_update_dotation_projets_from_projet_accepted_removes_dotation_projets_if_accepted_or_dismissed(
    perimetres,
    dotation_status,
):
    """Test _update_dotation_projets_from_projet_accepted removes dotation projets if accepted or processing"""
    # Arrange
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        demande_dispositif_sollicite="DETR et DSIL",
        ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)

    dps._initialize_dotation_projets_from_projet(projet)
    assert projet.dotationprojet_set.count() == 2

    projet.dotationprojet_set.filter(dotation=DOTATION_DSIL).update(
        status=dotation_status
    )

    # Act
    projet.dossier_ds.annotations_dotation = "DETR"
    projet.dossier_ds.annotations_assiette_detr = 10_000
    projet.dossier_ds.annotations_montant_accorde_detr = 5_000
    projet.dossier_ds.save()

    dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    # Assert
    assert len(dotation_projets) == 1
    assert projet.dotationprojet_set.count() == 1
    assert DotationProjet.objects.filter(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    ).exists()
    assert not DotationProjet.objects.filter(
        projet=projet, dotation=DOTATION_DSIL
    ).exists()


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_accepted_with_empty_annotations_dotation_falls_back(
    perimetres,
    caplog,
):
    """Test _update_dotation_projets_from_projet_accepted falls back to demande_dispositif_sollicite when annotations_dotation is empty"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="DETR",
        dossier_ds__ds_date_traitement=None,
        dossier_ds__perimetre=arr_dijon,
    )

    dps._initialize_dotation_projets_from_projet(projet)
    assert projet.dotationprojet_set.count() == 1

    projet.dossier_ds.ds_state = Dossier.STATE_ACCEPTE
    projet.dossier_ds.ds_date_traitement = timezone.datetime(2025, 1, 15, tzinfo=UTC)
    projet.dossier_ds.annotations_dotation = ""
    projet.dossier_ds.save()

    # --

    with caplog.at_level(logging.WARNING):
        dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    # --

    assert len(dotation_projets) == 1
    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_PROCESSING

    assert len(caplog.records) == 2
    record = caplog.records[0]
    assert record.message == "Assiette is missing in dossier annotations"
    assert record.levelname == "INFO", (
        "Log level should be INFO because the dossier is in EN_INSTRUCTION during initialization"
    )

    record = caplog.records[1]
    assert (
        record.message
        == "No dotations found in annotations_dotation for accepted dossier during update"
    )
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "projet", None) == projet.pk


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_refused(perimetres):
    """Test _update_dotation_projets_from_projet_refused"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create existing dotation projets with different statuses
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_refused(projet)

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_REFUSED

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_refused_does_not_update_already_refused(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_refused does not update already refused dotation projets"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create already refused dotation projet
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_refused(projet)

    assert len(dotation_projets) == 1
    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_sans_suite(perimetres):
    """Test _update_dotation_projets_from_projet_sans_suite"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create existing dotation projets with different statuses
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_sans_suite(projet)

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_DISMISSED

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_DISMISSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_sans_suite_does_not_update_already_dismissed_or_refused(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_sans_suite does not update already dismissed or refused dotation projets"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create already dismissed and refused dotation projets
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_DISMISSED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_REFUSED
    )

    dotation_projets = dps._update_dotation_projets_from_projet(projet)

    assert len(dotation_projets) == 2
    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_DISMISSED
    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status_1, status_2",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_REFUSED),
    ),
)
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_back_to_instruction(
    perimetres, status_1, status_2
):
    """Test _update_dotation_projets_from_projet_back_to_instruction"""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 10, tzinfo=UTC),
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, tzinfo=UTC
        ),
    )

    # Create dotation projets with different statuses
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=status_1
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=status_2
    )

    dotation_projets = dps._update_dotation_projets_from_projet(projet)

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_PROCESSING

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_PROCESSING


@pytest.mark.parametrize(
    "refused_or_dismissed", (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED)
)
@pytest.mark.django_db
def test_update_dotation_projets_from_projet_back_to_instruction_with_one_accepted_and_one_dismissed(
    perimetres,
    refused_or_dismissed,
):
    """Test _update_dotation_projets_from_projet_back_to_instruction with one accepted and one dismissed"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 10, tzinfo=UTC),
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, tzinfo=UTC
        ),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create one accepted and one dismissed dotation projet
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=refused_or_dismissed
    )

    dotation_projets = dps._update_dotation_projets_from_projet_back_to_instruction(
        projet
    )

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_PROCESSING

    dsil_dp.refresh_from_db()
    # The dismissed one should remain dismissed (not updated)
    assert dsil_dp.status == refused_or_dismissed


@pytest.mark.parametrize(
    "first_status, second_status",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED),
    ),
)
@pytest.mark.django_db
def test_update_dotation_projets_from_projet_back_to_instruction_with_a_programmation_projet_created_after_date_of_passage_en_instruction(
    perimetres,
    first_status,
    second_status,
):
    arr_dijon, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 20, tzinfo=UTC
        ),
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create two accepted dotation projets
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=first_status
    )
    with freeze_time("2025-01-25"):
        ProgrammationProjetFactory.create(dotation_projet=detr_dp)

    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=second_status
    )
    with freeze_time("2025-01-10"):
        ProgrammationProjetFactory.create(dotation_projet=dsil_dp)

    # --

    dotation_projets = dps._update_dotation_projets_from_projet(projet)

    # --

    assert len(dotation_projets) == 2
    detr_dp.refresh_from_db()
    assert detr_dp.status == first_status, (
        "The dotation projet with status %s should remain %s because the programmation_projet was created before the date of passage en instruction"
        % (first_status, first_status)
    )

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_PROCESSING, (
        "The dotation projet with status %s should be set to processing because the programmation_projet was created after the date of passage en instruction"
        % second_status
    )
    assert hasattr(dsil_dp, "programmation_projet") is False


@pytest.mark.parametrize(
    "second_status",
    (PROJET_STATUS_DISMISSED, PROJET_STATUS_REFUSED),
)
@pytest.mark.django_db
def test_update_dotation_projets_from_projet_back_to_instruction_with_one_accepted_and_programmation_projet_created_after_date_of_passage_en_instruction_and_one_dismissed_or_refused(
    perimetres,
    second_status,
):
    """Test _update_dotation_projets_from_projet_back_to_instruction with two accepted dotation projets and one programmation_projet created after date of passage en instruction"""
    arr_dijon, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 20, tzinfo=UTC
        ),
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create two accepted dotation projets
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    with freeze_time("2025-01-25"):
        ProgrammationProjetFactory.create(dotation_projet=detr_dp)

    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=second_status
    )
    with freeze_time("2025-01-10"):
        ProgrammationProjetFactory.create(dotation_projet=dsil_dp)

    # --

    dotation_projets = dps._update_dotation_projets_from_projet(projet)

    # --

    assert len(dotation_projets) == 1
    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_ACCEPTED, (
        "The accepted dotation projet should remain accepted because the programmation_projet was created before the date of passage en instruction"
    )

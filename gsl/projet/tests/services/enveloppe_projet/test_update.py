import logging
from datetime import UTC

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl.core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.historique.models import ProjetAction
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.simulation.models import SimulationProjet
from gsl.simulation.tests.factories import SimulationFactory
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ....constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ....models import EnveloppeProjet
from ....services.enveloppe_projet_services import EnveloppeProjetService
from ...factories import (
    EnveloppeProjetFactory,
    ProjetFactory,
)

synchroniser = EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet


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


# -- accepted dossier — ProjetAction dotation --


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_creates_dotation_added_action_for_new_dotation(perimetres):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.State.ACCEPTE,
        demande_dispositif_sollicite="DETR et DSIL",
        annotations_dotation="DETR et DSIL",
        annotations_assiette_detr=10_000,
        annotations_montant_accorde_detr=5_000,
        annotations_assiette_dsil=20_000,
        annotations_montant_accorde_dsil=10_000,
        ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    synchroniser(projet)
    assert projet.enveloppeprojet_set.count() == 2

    # Simulate DN adding DSIL after initial import had only DETR
    projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).delete()
    assert projet.enveloppeprojet_set.count() == 1

    synchroniser(projet)

    actions = ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_DOTATION_ADDED
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.dotation == DOTATION_DSIL
    assert action.source == ProjetAction.SOURCE_DN
    assert action.actor is None

    dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()
    assert dsil.status == ProjetStatus.ACCEPTED
    assert dsil.montant == 10_000


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_creates_dotation_removed_action_when_dotation_dropped(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.State.ACCEPTE,
        demande_dispositif_sollicite="DETR et DSIL",
        annotations_dotation="DETR",
        annotations_assiette_detr=10_000,
        annotations_montant_accorde_detr=5_000,
        ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.PROCESSING
    )

    synchroniser(projet)

    actions = ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_DOTATION_REMOVED
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.dotation == DOTATION_DSIL
    assert action.source == ProjetAction.SOURCE_DN
    assert action.actor is None


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_does_not_create_removed_action_for_already_refused_dotation(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.State.ACCEPTE,
        demande_dispositif_sollicite="DETR",
        annotations_dotation="DETR",
        annotations_assiette_detr=10_000,
        annotations_montant_accorde_detr=5_000,
        ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.REFUSED
    )

    synchroniser(projet)

    assert (
        ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_DOTATION_REMOVED
        ).count()
        == 0
    )


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_creates_new_enveloppe_projets(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.State.EN_INSTRUCTION,
        demande_dispositif_sollicite="DETR",
        annotations_assiette_detr=None,
        annotations_montant_accorde_detr=None,
        ds_date_traitement=None,
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(
        dossier_ds=dossier,
    )

    synchroniser(projet)
    assert projet.enveloppeprojet_set.count() == 1

    # Projet has been accepted on DN for DETR and DSIL
    dossier.ds_state = Dossier.State.ACCEPTE
    dossier.annotations_dotation = "DETR et DSIL"
    dossier.annotations_assiette_detr = 10_000
    dossier.annotations_montant_accorde_detr = 5_000
    dossier.annotations_assiette_dsil = 20_000
    dossier.annotations_montant_accorde_dsil = 15_000
    dossier.ds_date_traitement = timezone.datetime(2025, 1, 15, tzinfo=UTC)
    dossier.save()

    synchroniser(projet)

    assert projet.enveloppeprojet_set.count() == 2

    detr_dp = EnveloppeProjet.objects.for_dotation(DOTATION_DETR).get(projet=projet)
    assert detr_dp.status == ProjetStatus.ACCEPTED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 5_000
    assert detr_dp.taux_retenu == 50

    dsil_dp = EnveloppeProjet.objects.for_dotation(DOTATION_DSIL).get(projet=projet)
    assert dsil_dp.status == ProjetStatus.ACCEPTED
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.montant_retenu == 15_000
    assert dsil_dp.taux_retenu == 75


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "dotation_status",
    (ProjetStatus.REFUSED, ProjetStatus.DISMISSED),
)
def test_update_accepted_keeps_enveloppe_projets_not_annotated_if_refused_or_dismissed(
    perimetres,
    dotation_status,
):
    # Arrange
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    dossier = DossierFactory(
        ds_state=Dossier.State.EN_INSTRUCTION,
        demande_dispositif_sollicite="DETR et DSIL",
        ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)

    synchroniser(projet)
    assert projet.enveloppeprojet_set.count() == 2

    projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).update(
        status=dotation_status,
        enveloppe=dsil_enveloppe,
        date_programmation=timezone.now(),
    )

    # Act
    projet.dossier_ds.ds_state = Dossier.State.ACCEPTE
    projet.dossier_ds.annotations_dotation = "DETR"
    projet.dossier_ds.annotations_assiette_detr = 10_000
    projet.dossier_ds.annotations_montant_accorde_detr = 5_000
    projet.dossier_ds.save()

    synchroniser(projet)

    # Assert
    assert projet.enveloppeprojet_set.count() == 2
    assert (
        EnveloppeProjet.objects.for_dotation(DOTATION_DETR)
        .filter(projet=projet, status=ProjetStatus.ACCEPTED)
        .exists()
    )
    assert (
        EnveloppeProjet.objects.for_dotation(DOTATION_DSIL)
        .filter(projet=projet, status=dotation_status)
        .exists()
    )


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_removes_enveloppe_projet_not_annotated_if_processing(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")

    _accept_on_dn(
        projet, annotations_dotation="DETR", annotations_montant_accorde_detr=5_000
    )
    synchroniser(projet)

    detr = projet.enveloppeprojet_set.get()
    assert detr.dotation == DOTATION_DETR
    assert detr.status == ProjetStatus.ACCEPTED
    assert not EnveloppeProjet.all_objects.for_dotation(DOTATION_DSIL).exists()


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_refuses_accepted_enveloppe_projet_not_annotated_and_keeps_it_as_history(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    simulation = SimulationFactory(enveloppe=dsil_enveloppe)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")
    _accept_on_dn(
        projet,
        annotations_dotation="DETR et DSIL",
        annotations_montant_accorde_detr=5_000,
        annotations_montant_accorde_dsil=10_000,
    )
    synchroniser(projet)
    ancienne_dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()

    _accept_on_dn(projet, annotations_dotation="DETR")
    synchroniser(projet)

    assert projet.enveloppeprojet_set.for_dotation(DOTATION_DETR).get().status == (
        ProjetStatus.ACCEPTED
    )

    ancienne_dsil.refresh_from_db()
    assert ancienne_dsil.is_courant is False
    assert ancienne_dsil.status == ProjetStatus.ACCEPTED
    assert ancienne_dsil.montant == 10_000

    nouvelle_dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()
    assert nouvelle_dsil.pk != ancienne_dsil.pk
    assert nouvelle_dsil.status == ProjetStatus.REFUSED

    simulation_projet = SimulationProjet.objects.get(simulation=simulation)
    assert simulation_projet.enveloppe_projet == nouvelle_dsil
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED

    dsil_actions = ProjetAction.objects.filter(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_actions.filter(
        action_type=ProjetAction.TYPE_STATUS_CHANGE,
        status=ProjetStatus.REFUSED,
        source=ProjetAction.SOURCE_DN,
    ).exists()
    assert not dsil_actions.filter(
        action_type=ProjetAction.TYPE_DOTATION_REMOVED
    ).exists()


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_accepted_double_dotation_with_both_annotated_accepts_both(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")

    _accept_on_dn(
        projet,
        annotations_dotation="DETR et DSIL",
        annotations_montant_accorde_detr=5_000,
        annotations_montant_accorde_dsil=None,
    )
    synchroniser(projet)

    detr = projet.enveloppeprojet_set.for_dotation(DOTATION_DETR).get()
    assert detr.status == ProjetStatus.ACCEPTED
    assert detr.montant == 5_000
    dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()
    assert dsil.status == ProjetStatus.ACCEPTED
    assert dsil.montant == 0


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "initial_dsil_status, expected_dsil_actions",
    (
        (ProjetStatus.PROCESSING, [ProjetStatus.ACCEPTED]),
        (ProjetStatus.REFUSED, [ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED]),
        (ProjetStatus.DISMISSED, [ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED]),
        (ProjetStatus.ACCEPTED, []),
    ),
)
def test_update_accepted_accepts_annotated_dotation_whatever_its_status(
    perimetres, initial_dsil_status, expected_dsil_actions
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")
    _force_status(projet, DOTATION_DSIL, initial_dsil_status, dsil_enveloppe)
    ancienne_detr = projet.enveloppeprojet_set.for_dotation(DOTATION_DETR).get()
    ancienne_dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()

    _accept_on_dn(
        projet,
        annotations_dotation="DETR et DSIL",
        annotations_montant_accorde_dsil=4_000,
    )
    synchroniser(projet)

    _assert_treated_from_dn(
        projet, ancienne_detr, ProjetStatus.ACCEPTED, [ProjetStatus.ACCEPTED]
    )
    _assert_treated_from_dn(
        projet, ancienne_dsil, ProjetStatus.ACCEPTED, expected_dsil_actions
    )


# -- accepted dossier — single dotation --


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "dotation, montant_field",
    (
        (DOTATION_DETR, "annotations_montant_accorde_detr"),
        (DOTATION_DSIL, "annotations_montant_accorde_dsil"),
    ),
)
@pytest.mark.parametrize(
    "montant_annote, expected_montant",
    ((5_000, 5_000), (None, 0)),
)
def test_update_accepted_single_dotation_accepts_annotated_dotation(
    perimetres, dotation, montant_field, montant_annote, expected_montant
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande=dotation)

    _accept_on_dn(
        projet, annotations_dotation=dotation, **{montant_field: montant_annote}
    )
    synchroniser(projet)

    enveloppe_projet = projet.enveloppeprojet_set.get()
    assert enveloppe_projet.status == ProjetStatus.ACCEPTED
    assert enveloppe_projet.montant == expected_montant


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "initial_status, expected_status, expected_montant",
    (
        (ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED, 0),
        (ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED, 4_000),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED, None),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED, None),
    ),
)
def test_update_accepted_single_dotation_with_empty_annotations_dotation_accepts_it_if_processing(
    perimetres, caplog, initial_status, expected_status, expected_montant
):
    arr_dijon, dep_21, *_ = perimetres
    detr_enveloppe = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR")
    _force_status(projet, DOTATION_DETR, initial_status, detr_enveloppe)

    _accept_on_dn(projet, annotations_dotation="")
    with caplog.at_level(logging.WARNING):
        synchroniser(projet)

    detr = projet.enveloppeprojet_set.get()
    assert detr.status == expected_status
    assert detr.montant == expected_montant
    _assert_empty_annotations_dotation_warning(caplog, projet)


# -- accepted dossier — double dotation with empty annotations_dotation --


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "initial_dsil_status, expected_dsil_status",
    (
        (ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED),
    ),
)
def test_update_accepted_double_dotation_with_empty_annotations_dotation_accepts_the_processing_ones(
    perimetres, caplog, initial_dsil_status, expected_dsil_status
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")
    _force_status(projet, DOTATION_DSIL, initial_dsil_status, dsil_enveloppe)

    _accept_on_dn(projet, annotations_dotation="")
    with caplog.at_level(logging.WARNING):
        synchroniser(projet)

    assert projet.enveloppeprojet_set.for_dotation(DOTATION_DETR).get().status == (
        ProjetStatus.ACCEPTED
    )
    assert projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get().status == (
        expected_dsil_status
    )
    _assert_empty_annotations_dotation_warning(caplog, projet)


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "initial_dsil_status, expected_dsil_actions",
    (
        (ProjetStatus.PROCESSING, [ProjetStatus.REFUSED]),
        (ProjetStatus.DISMISSED, [ProjetStatus.PROCESSING, ProjetStatus.REFUSED]),
        (ProjetStatus.REFUSED, []),
        (ProjetStatus.ACCEPTED, [ProjetStatus.PROCESSING, ProjetStatus.REFUSED]),
    ),
)
def test_update_refused_refuses_every_dotation(
    perimetres, initial_dsil_status, expected_dsil_actions
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")
    _force_status(projet, DOTATION_DSIL, initial_dsil_status, dsil_enveloppe)
    ancienne_detr = projet.enveloppeprojet_set.for_dotation(DOTATION_DETR).get()
    ancienne_dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()

    _treat_on_dn(projet, Dossier.State.REFUSE)
    synchroniser(projet)

    _assert_treated_from_dn(
        projet, ancienne_detr, ProjetStatus.REFUSED, [ProjetStatus.REFUSED]
    )
    _assert_treated_from_dn(
        projet, ancienne_dsil, ProjetStatus.REFUSED, expected_dsil_actions
    )


@pytest.mark.django_db
@freeze_time("2025-05-06")
@pytest.mark.parametrize(
    "initial_dsil_status, expected_dsil_status, expected_dsil_actions",
    (
        (ProjetStatus.PROCESSING, ProjetStatus.DISMISSED, [ProjetStatus.DISMISSED]),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED, []),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED, []),
        (
            ProjetStatus.ACCEPTED,
            ProjetStatus.DISMISSED,
            [ProjetStatus.PROCESSING, ProjetStatus.DISMISSED],
        ),
    ),
)
def test_update_sans_suite_dismisses_every_dotation_not_refused(
    perimetres, initial_dsil_status, expected_dsil_status, expected_dsil_actions
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = _synchronised_projet_en_instruction(arr_dijon, demande="DETR et DSIL")
    _force_status(projet, DOTATION_DSIL, initial_dsil_status, dsil_enveloppe)
    ancienne_detr = projet.enveloppeprojet_set.for_dotation(DOTATION_DETR).get()
    ancienne_dsil = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()

    _treat_on_dn(projet, Dossier.State.SANS_SUITE)
    synchroniser(projet)

    _assert_treated_from_dn(
        projet, ancienne_detr, ProjetStatus.DISMISSED, [ProjetStatus.DISMISSED]
    )
    _assert_treated_from_dn(
        projet, ancienne_dsil, expected_dsil_status, expected_dsil_actions
    )


def date_programmation_avant_instruction(status):
    if status == ProjetStatus.PROCESSING:
        return None
    return timezone.datetime(2025, 1, 10, tzinfo=UTC)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status_1, status_2",
    (
        (ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED),
        (ProjetStatus.REFUSED, ProjetStatus.DISMISSED),
        (ProjetStatus.PROCESSING, ProjetStatus.DISMISSED),
        (ProjetStatus.PROCESSING, ProjetStatus.REFUSED),
    ),
)
@freeze_time("2025-05-06")
def test_update_back_to_instruction(perimetres, status_1, status_2):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 10, tzinfo=UTC),
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, tzinfo=UTC
        ),
    )

    # Create enveloppe projets with different statuses, programmed before the
    # passage en instruction so none of them is kept as is.
    detr_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=status_1,
        date_programmation=date_programmation_avant_instruction(status_1),
    )
    dsil_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DSIL,
        status=status_2,
        date_programmation=date_programmation_avant_instruction(status_2),
    )

    synchroniser(projet)

    detr_dp = courant(detr_dp)
    assert detr_dp.status == ProjetStatus.PROCESSING

    dsil_dp = courant(dsil_dp)
    assert dsil_dp.status == ProjetStatus.PROCESSING


@pytest.mark.parametrize(
    "refused_or_dismissed", (ProjetStatus.REFUSED, ProjetStatus.DISMISSED)
)
@pytest.mark.django_db
def test_update_back_to_instruction_with_one_accepted_and_one_dismissed(
    perimetres,
    refused_or_dismissed,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 10, tzinfo=UTC),
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, tzinfo=UTC
        ),
        dossier_ds__perimetre=arr_dijon,
    )

    # Create one accepted and one dismissed enveloppe projet, both programmed
    # before the passage en instruction.
    detr_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        date_programmation=timezone.datetime(2025, 1, 10, tzinfo=UTC),
    )
    dsil_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DSIL,
        status=refused_or_dismissed,
        date_programmation=timezone.datetime(2025, 1, 10, tzinfo=UTC),
    )

    synchroniser(projet)

    detr_dp = courant(detr_dp)
    assert detr_dp.status == ProjetStatus.PROCESSING

    dsil_dp = courant(dsil_dp)
    # The dismissed one should remain dismissed (not updated)
    assert dsil_dp.status == refused_or_dismissed


@pytest.mark.parametrize(
    "first_status, second_status",
    (
        (ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED),
        (ProjetStatus.DISMISSED, ProjetStatus.ACCEPTED),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED),
        (ProjetStatus.DISMISSED, ProjetStatus.REFUSED),
        (ProjetStatus.REFUSED, ProjetStatus.ACCEPTED),
        (ProjetStatus.REFUSED, ProjetStatus.DISMISSED),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED),
    ),
)
@pytest.mark.django_db
def test_update_back_to_instruction_with_a_programmation_after_date_of_passage_en_instruction(
    perimetres,
    first_status,
    second_status,
):
    arr_dijon, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 20, tzinfo=UTC
        ),
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    detr_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=first_status,
        date_programmation=timezone.datetime(2025, 1, 25, tzinfo=UTC),
    )
    dsil_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DSIL,
        status=second_status,
        date_programmation=timezone.datetime(2025, 1, 10, tzinfo=UTC),
    )

    # --

    synchroniser(projet)

    # --

    detr_dp = courant(detr_dp)
    assert detr_dp.status == first_status, (
        "The enveloppe projet with status %s should remain %s because it was programmed after the date of passage en instruction"
        % (first_status, first_status)
    )

    dsil_dp = courant(dsil_dp)
    assert dsil_dp.status == ProjetStatus.PROCESSING, (
        "The enveloppe projet with status %s should be set to processing because it was programmed before the date of passage en instruction"
        % second_status
    )
    assert dsil_dp.is_programmee is False


@pytest.mark.parametrize(
    "second_status",
    (ProjetStatus.DISMISSED, ProjetStatus.REFUSED),
)
@pytest.mark.django_db
def test_update_back_to_instruction_with_one_accepted_and_programmation_after_date_of_passage_en_instruction_and_one_dismissed_or_refused(
    perimetres,
    second_status,
):
    arr_dijon, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 20, tzinfo=UTC
        ),
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        dossier_ds__perimetre=arr_dijon,
    )

    detr_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        date_programmation=timezone.datetime(2025, 1, 25, tzinfo=UTC),
    )
    dsil_dp = EnveloppeProjetFactory(
        projet=projet,
        dotation=DOTATION_DSIL,
        status=second_status,
        date_programmation=timezone.datetime(2025, 1, 10, tzinfo=UTC),
    )

    # --

    synchroniser(projet)

    # --

    detr_dp.refresh_from_db()
    assert detr_dp.status == ProjetStatus.ACCEPTED, (
        "The accepted enveloppe projet should remain accepted because it was programmed after the date of passage en instruction"
    )
    dsil_dp.refresh_from_db()
    assert dsil_dp.status == second_status


# -- assiette history --


@pytest.mark.django_db
def test_update_assiette_creates_action_when_assiette_changes():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=10_000,
        projet__dossier_ds__annotations_assiette_detr=20_000,
    )

    synchroniser(enveloppe_projet.projet)

    actions = ProjetAction.objects.filter(
        projet=enveloppe_projet.projet,
        action_type=ProjetAction.TYPE_ASSIETTE_MODIFIED,
        dotation=DOTATION_DETR,
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.euro_field_value == 20_000
    assert action.source == ProjetAction.SOURCE_DN
    assert action.actor is None


@pytest.mark.django_db
def test_update_assiette_does_not_create_action_when_assiette_unchanged():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=10_000,
        projet__dossier_ds__annotations_assiette_detr=10_000,
    )

    synchroniser(enveloppe_projet.projet)

    assert (
        ProjetAction.objects.filter(
            projet=enveloppe_projet.projet,
            action_type=ProjetAction.TYPE_ASSIETTE_MODIFIED,
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_update_assiette_creates_action_when_assiette_changed():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=10_000,
        projet__dossier_ds__annotations_assiette_detr=15_000,
    )

    synchroniser(enveloppe_projet.projet)

    actions = ProjetAction.objects.filter(
        projet=enveloppe_projet.projet,
        action_type=ProjetAction.TYPE_ASSIETTE_MODIFIED,
    )
    assert actions.count() == 1
    assert actions.first().euro_field_value == 15_000


def courant(enveloppe_projet: EnveloppeProjet) -> EnveloppeProjet:
    """A reopened EnveloppeProjet is replaced by a new courant one."""
    return EnveloppeProjet.objects.get(
        projet=enveloppe_projet.projet, enveloppe__dotation=enveloppe_projet.dotation
    )


# -- helpers --


def _synchronised_projet_en_instruction(perimetre, demande):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__demande_dispositif_sollicite=demande,
        dossier_ds__ds_date_traitement=None,
        dossier_ds__perimetre=perimetre,
    )
    synchroniser(projet)
    return projet


def _accept_on_dn(projet, annotations_dotation, **annotations):
    _treat_on_dn(
        projet,
        Dossier.State.ACCEPTE,
        annotations_dotation=annotations_dotation,
        **annotations,
    )


def _treat_on_dn(projet, ds_state, **dossier_fields):
    dossier = projet.dossier_ds
    dossier.ds_state = ds_state
    dossier.ds_date_traitement = timezone.datetime(2025, 1, 15, tzinfo=UTC)
    for field, value in dossier_fields.items():
        setattr(dossier, field, value)
    dossier.save()


def _force_status(projet, dotation, status, enveloppe):
    if status == ProjetStatus.PROCESSING:
        return
    projet.enveloppeprojet_set.for_dotation(dotation).update(
        status=status,
        enveloppe=enveloppe,
        montant=4_000 if status == ProjetStatus.ACCEPTED else None,
        date_programmation=timezone.now(),
    )


def _assert_empty_annotations_dotation_warning(caplog, projet):
    record = next(
        record
        for record in caplog.records
        if record.message
        == "No dotations found in annotations_dotation for accepted dossier"
    )
    assert record.levelname == "WARNING"
    assert record.dossier_ds_number == projet.dossier_ds.ds_number
    assert record.projet == projet.pk


def _assert_treated_from_dn(projet, ancienne, expected_status, expected_status_actions):
    """A treated dotation changing status is kept as history and replaced by a new
    one, set back to processing then treated: hence two status change actions."""
    courante = projet.enveloppeprojet_set.for_dotation(ancienne.dotation).get()
    assert courante.status == expected_status

    is_replaced = ProjetStatus.PROCESSING in expected_status_actions
    assert (courante.pk != ancienne.pk) is is_replaced
    ancienne.refresh_from_db()
    assert ancienne.is_courant is not is_replaced

    status_actions = ProjetAction.objects.filter(
        projet=projet,
        dotation=ancienne.dotation,
        action_type=ProjetAction.TYPE_STATUS_CHANGE,
        source=ProjetAction.SOURCE_DN,
    ).order_by("pk")
    assert [action.status for action in status_actions] == expected_status_actions

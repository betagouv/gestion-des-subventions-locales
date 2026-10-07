import datetime
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
from gsl.simulation.models import Simulation, SimulationProjet
from gsl.simulation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_demarches_simplifiees.models import Dossier

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

CURRENT_YEAR = datetime.datetime.now().year

synchroniser = EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet


def simulations_de(enveloppe_projet):
    return Simulation.objects.filter(
        simulationprojet__enveloppe_projet=enveloppe_projet
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


# -- create_or_update_enveloppe_projet_from_projet --


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "dotation_value, enveloppe_projet_count",
    (
        ("DETR", 1),
        ("['DETR']", 1),
        ("DSIL", 1),
        ("['DSIL']", 1),
        ("[DETR, DSIL]", 2),
        ("DETR et DSIL", 2),
        ("['DETR', 'DSIL', 'DETR et DSIL']", 2),
    ),
)
def test_create_or_update_enveloppe_projet_from_projet(
    field,
    dotation_value,
    enveloppe_projet_count,
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=CURRENT_YEAR)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=CURRENT_YEAR)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.ACCEPTE,
        dossier_ds__annotations_assiette_detr=1_000,
        dossier_ds__annotations_assiette_dsil=1_000,
        dossier_ds__perimetre=arr_dijon,
    )
    setattr(projet.dossier_ds, field, dotation_value)

    synchroniser(projet)

    assert EnveloppeProjet.objects.count() == enveloppe_projet_count

    for enveloppe_projet in EnveloppeProjet.objects.all():
        assert enveloppe_projet.projet == projet
        assert enveloppe_projet.status == ProjetStatus.ACCEPTED
        assert enveloppe_projet.assiette == 1_000
        if enveloppe_projet.dotation == DOTATION_DSIL:
            assert enveloppe_projet.detr_avis_commission is None
        else:
            assert enveloppe_projet.detr_avis_commission is True


@pytest.mark.django_db
def test_create_or_update_enveloppe_projet_from_en_instruction_projet_ignore_annotations():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__annotations_dotation="DETR",
    )
    projet_dotation_dsil = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    projet_enveloppe_projets = EnveloppeProjet.objects.filter(projet=projet)
    assert projet_enveloppe_projets.count() == 1

    synchroniser(projet)

    projet_dotation_dsil.refresh_from_db()  # always exists

    projet_enveloppe_projets = EnveloppeProjet.objects.filter(projet_id=projet.id)
    assert projet_enveloppe_projets.count() == 1

    dsil_enveloppe_projets = projet_enveloppe_projets.for_dotation(DOTATION_DSIL)
    assert dsil_enveloppe_projets.count() == 1

    detr_enveloppe_projet = projet_enveloppe_projets.for_dotation(DOTATION_DETR)
    assert detr_enveloppe_projet.count() == 0


@pytest.mark.django_db
def test_create_or_update_enveloppe_projet_from_projet_also_refuse_dsil_enveloppe_projet_even_if_not_in_demande_dispositif_sollicite(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=CURRENT_YEAR)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=CURRENT_YEAR)
    projet = ProjetFactory(
        dossier_ds__perimetre=arr_dijon,
        dossier_ds__ds_state=Dossier.State.REFUSE,
        dossier_ds__demande_dispositif_sollicite="DETR",
    )
    projet_dotation_detr = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )
    projet_dotation_dsil = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.PROCESSING
    )
    projet_enveloppe_projets = EnveloppeProjet.objects.filter(projet=projet)
    assert projet_enveloppe_projets.count() == 2

    synchroniser(projet)

    projet_dotation_detr.refresh_from_db()  # always exists
    assert projet_dotation_detr.status == ProjetStatus.REFUSED

    projet_dotation_dsil.refresh_from_db()  # always exists
    assert projet_dotation_dsil.status == ProjetStatus.REFUSED


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize(
    "dossier_state",
    (
        Dossier.State.ACCEPTE,
        Dossier.State.EN_CONSTRUCTION,
        Dossier.State.EN_INSTRUCTION,
        Dossier.State.REFUSE,
        Dossier.State.SANS_SUITE,
    ),
)
@pytest.mark.django_db
def test_detr_avis_commission_is_set_only_for_accepted_detr(dotation, dossier_state):
    projet = ProjetFactory(
        dossier_ds__ds_state=dossier_state,
        dossier_ds__demande_dispositif_sollicite=dotation,
        dossier_ds__annotations_dotation=dotation,
    )

    synchroniser(projet)

    enveloppe_projet = projet.enveloppeprojet_set.get()
    if dotation == DOTATION_DETR and dossier_state == Dossier.State.ACCEPTE:
        assert enveloppe_projet.detr_avis_commission is True
    else:
        assert enveloppe_projet.detr_avis_commission is None


# -- dotations of an en construction dossier --


@pytest.mark.django_db
def test_create_or_update_enveloppe_projet_syncs_from_dn_when_dossier_updated_in_construction_detr_to_dsil(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
        dossier_ds__perimetre=arr_dijon,
    )
    assert projet.dotations_updated_in_app is False
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    enveloppe_projets = projet.enveloppeprojet_set.all()
    assert enveloppe_projets.count() == 1
    assert enveloppe_projets.first().dotation == DOTATION_DSIL


@pytest.mark.django_db
def test_create_or_update_enveloppe_projet_syncs_from_dn_when_dossier_updated_in_construction_dsil_to_detr_and_dsil(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
        dossier_ds__perimetre=arr_dijon,
    )
    assert projet.dotations_updated_in_app is False
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    synchroniser(projet)

    enveloppe_projets = projet.enveloppeprojet_set.all()
    assert enveloppe_projets.count() == 2
    assert set(projet.dotations) == {DOTATION_DETR, DOTATION_DSIL}


@pytest.mark.django_db
def test_create_or_update_enveloppe_projet_syncs_from_dn_when_dossier_updated_in_construction_detr_and_dsil_to_dsil(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
        dossier_ds__perimetre=arr_dijon,
    )
    assert projet.dotations_updated_in_app is False
    detr_dp = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dsil_dp = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    synchroniser(projet)

    assert not EnveloppeProjet.objects.filter(pk=detr_dp.pk).exists()
    assert EnveloppeProjet.objects.filter(pk=dsil_dp.pk).exists()
    assert projet.dotations == [DOTATION_DSIL]


@pytest.mark.django_db
def test_dotations_are_not_synced_from_dn_once_updated_in_app():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
        dotations_updated_in_app=True,
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    assert projet.dotations == [DOTATION_DETR]


@pytest.mark.django_db
def test_dotations_are_not_synced_from_dn_when_not_en_construction():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    assert projet.dotations == [DOTATION_DETR]


@pytest.mark.django_db
def test_dotations_are_kept_when_they_match_the_dossier():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR']",
    )
    detr_dp = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    assert EnveloppeProjet.objects.filter(pk=detr_dp.pk).exists()
    assert projet.dotations == [DOTATION_DETR]


@pytest.mark.django_db
def test_dotations_are_kept_when_both_match_the_dossier():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    synchroniser(projet)

    assert projet.dotations == [DOTATION_DETR, DOTATION_DSIL]


@pytest.mark.django_db
def test_dotation_added_from_dn_gets_assiette_from_dossier():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    dsil_dp = projet.enveloppeprojet_set.for_dotation(DOTATION_DSIL).get()
    assert dsil_dp.assiette == 20_000


@pytest.mark.django_db
def test_dotation_removed_from_dn_creates_removed_action():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    synchroniser(projet)

    actions = ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_DOTATION_REMOVED
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.dotation == DOTATION_DETR
    assert action.source == ProjetAction.SOURCE_DN
    assert action.actor is None


@pytest.mark.django_db
def test_dotation_added_from_dn_creates_added_action():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    actions = ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_DOTATION_ADDED
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.dotation == DOTATION_DSIL
    assert action.source == ProjetAction.SOURCE_DN
    assert action.actor is None


@pytest.mark.django_db
def test_dotations_unchanged_creates_no_dotation_action():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.State.EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR']",
    )
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)

    synchroniser(projet)

    assert (
        ProjetAction.objects.filter(
            projet=projet,
            action_type__in=[
                ProjetAction.TYPE_DOTATION_ADDED,
                ProjetAction.TYPE_DOTATION_REMOVED,
            ],
        ).count()
        == 0
    )


# -- assiette --


@pytest.mark.django_db
def test_update_assiette_from_dossier_single_detr():
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=15_000,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, assiette=0
    )

    synchroniser(projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.assiette == 15_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_single_dsil():
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=15_000,
        dossier_ds__annotations_assiette_dsil=25_000,
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, assiette=0
    )

    synchroniser(projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.assiette == 25_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_both_dotations():
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=30_000,
    )
    dp_detr = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR, assiette=0)
    dp_dsil = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL, assiette=0)

    synchroniser(projet)

    dp_detr.refresh_from_db()
    dp_dsil.refresh_from_db()
    assert dp_detr.assiette == 10_000
    assert dp_dsil.assiette == 30_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_keeps_existing_assiette_when_missing_in_dossier():
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, assiette=5_000
    )

    synchroniser(projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.assiette == 5_000


# -- simulations of an enveloppe projet --


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_are_filtered_by_perimetre(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, arr_nanterre, dep_92, region_idf = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_arr_dijon = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_dep_21 = SimulationFactory(
        enveloppe__perimetre=dep_21,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    # This should not be included (different perimetre hierarchy)
    sim_arr_nanterre = SimulationFactory(
        enveloppe__perimetre=arr_nanterre,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    # Should include simulations with arr_dijon and dep_21 (ancestor)
    assert sim_arr_dijon in results
    assert sim_dep_21 in results
    # Should not include simulation with different perimetre
    assert sim_arr_nanterre not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_are_filtered_by_dotation(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_detr = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_dsil = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert sim_detr in results
    assert sim_dsil not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_are_filtered_by_year(
    perimetres,
):
    arr_dijon, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_current_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_next_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )
    sim_previous_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR - 1,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert sim_current_year in results
    assert sim_next_year in results
    assert sim_previous_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_with_department_perimetre(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        projet__dossier_ds__perimetre=dep_21,
    )

    sim_arr_dijon = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_dep_21 = SimulationFactory(
        enveloppe__perimetre=dep_21,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_region_bfc = SimulationFactory(
        enveloppe__perimetre=region_bfc,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    # Should include both department and region (ancestor)
    assert sim_dep_21 in results
    assert sim_region_bfc in results

    # Should not include arrondissement
    assert sim_arr_dijon not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_with_region_perimetre(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        projet__dossier_ds__perimetre=region_bfc,
    )

    sim_arr_dijon = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_dep_21 = SimulationFactory(
        enveloppe__perimetre=dep_21,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_region_bfc = SimulationFactory(
        enveloppe__perimetre=region_bfc,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )
    # Different region should not be included
    _, _, _, _, _, region_idf = perimetres
    sim_region_idf = SimulationFactory(
        enveloppe__perimetre=region_idf,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    # Only region should be included
    assert sim_region_bfc in results

    assert sim_arr_dijon not in results
    assert sim_dep_21 not in results
    assert sim_region_idf not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_combine_all_filters(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_valid = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    sim_wrong_dotation = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_wrong_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR - 1,
    )
    sim_dep_perimetre = SimulationFactory(
        enveloppe__perimetre=dep_21,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert sim_valid in results
    assert sim_wrong_dotation not in results
    assert sim_wrong_year not in results
    # dep_21 is an ancestor of arr_dijon
    assert sim_dep_perimetre in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "dossier_state",
    [Dossier.State.ACCEPTE, Dossier.State.SANS_SUITE, Dossier.State.REFUSE],
)
def test_simulations_exclude_future_years_for_terminal_state_with_treatment_date(
    perimetres, dossier_state
):
    arr_dijon, *_ = perimetres
    last_year = CURRENT_YEAR - 1

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=dossier_state,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            last_year, 6, 15, tzinfo=UTC
        ),
    )

    SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=last_year,
    )
    SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )

    synchroniser(enveloppe_projet.projet)

    assert simulations_de(enveloppe_projet).count() == 0, (
        "Should not include any simulations, because the dossier has been treated in the last year"
    )


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_do_not_exclude_future_years_without_treatment_date(
    perimetres,
):
    arr_dijon, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        projet__dossier_ds__ds_date_traitement=None,
    )

    sim_last_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR - 1,
    )
    sim_current_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_next_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert results.count() == 2, (
        "Should include all future years since there's no treatment date"
    )
    assert sim_current_year in results
    assert sim_next_year in results
    assert sim_last_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_do_not_exclude_future_years_when_not_terminal_state(
    perimetres,
):
    arr_dijon, *_ = perimetres
    treatment_year = CURRENT_YEAR - 1

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            treatment_year, 6, 15, tzinfo=UTC
        ),
    )

    sim_last_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR - 1,
    )
    sim_current_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_next_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert results.count() == 2, (
        "Should include all future years since dossier is not in terminal state"
    )
    assert sim_current_year in results
    assert sim_next_year in results
    assert sim_last_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_exclude_next_years_when_treatment_year_is_current_year(
    perimetres,
):
    arr_dijon, *_ = perimetres
    treatment_year = CURRENT_YEAR

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.ACCEPTE,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            treatment_year, 6, 15, tzinfo=UTC
        ),
    )

    _sim_last_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR - 1,
    )
    sim_current_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_next_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert results.count() == 1, (
        "Should include only current year since treatment year is current year"
    )
    assert sim_current_year in results
    assert sim_next_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_exclude_years_after_programmation_year(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_current_year = DetrEnveloppeFactory(
        perimetre=dep_21,
        annee=CURRENT_YEAR,
    )
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
        enveloppe=enveloppe_current_year,
    )

    sim_current_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_next_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert sim_current_year in results
    assert sim_next_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulations_include_all_next_years_when_no_programmation(
    perimetres,
):
    arr_dijon, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_current_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_next_year = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR + 1,
    )

    synchroniser(enveloppe_projet.projet)

    results = simulations_de(enveloppe_projet)
    assert sim_current_year in results
    assert sim_next_year in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulation_projets_are_removed_when_perimetre_changed(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, arr_nanterre, dep_92, region_idf = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_concerned = SimulationFactory(
        enveloppe__perimetre=dep_21,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_unconcerned = SimulationFactory(
        enveloppe__perimetre=dep_92,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    sp_concerned = SimulationProjetFactory(
        simulation=sim_concerned, enveloppe_projet=enveloppe_projet
    )
    sp_unconcerned = SimulationProjetFactory(
        simulation=sim_unconcerned, enveloppe_projet=enveloppe_projet
    )

    synchroniser(enveloppe_projet.projet)

    assert SimulationProjet.objects.filter(pk=sp_concerned.pk).exists()
    assert not SimulationProjet.objects.filter(pk=sp_unconcerned.pk).exists()


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulation_projets_are_kept_when_all_concerned(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_arr = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_dep = SimulationFactory(
        enveloppe__perimetre=dep_21,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    sp_arr = SimulationProjetFactory(
        simulation=sim_arr, enveloppe_projet=enveloppe_projet
    )
    sp_dep = SimulationProjetFactory(
        simulation=sim_dep, enveloppe_projet=enveloppe_projet
    )

    synchroniser(enveloppe_projet.projet)

    assert SimulationProjet.objects.filter(pk=sp_arr.pk).exists()
    assert SimulationProjet.objects.filter(pk=sp_dep.pk).exists()


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_simulation_projets_of_old_years_are_removed(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    sim_current = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_old = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR - 1,
    )

    sp_current = SimulationProjetFactory(
        simulation=sim_current, enveloppe_projet=enveloppe_projet
    )
    sp_old = SimulationProjetFactory(
        simulation=sim_old, enveloppe_projet=enveloppe_projet
    )

    synchroniser(enveloppe_projet.projet)

    assert SimulationProjet.objects.filter(pk=sp_current.pk).exists()
    assert not SimulationProjet.objects.filter(pk=sp_old.pk).exists()


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_no_simulation_projet_is_created_without_simulation(
    perimetres,
):
    arr_dijon, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    synchroniser(enveloppe_projet.projet)

    assert (
        SimulationProjet.objects.filter(enveloppe_projet=enveloppe_projet).count() == 0
    )


# -- back to instruction --


@pytest.mark.django_db
@pytest.mark.parametrize(
    "date_traitement, date_passage_en_instruction, expected_back_to_instruction",
    [
        (None, datetime.datetime(2024, 6, 1, tzinfo=UTC), False),
        (datetime.datetime(2024, 6, 1, tzinfo=UTC), None, False),
        (
            datetime.datetime(2024, 5, 1, tzinfo=UTC),
            datetime.datetime(2024, 6, 1, tzinfo=UTC),
            True,
        ),
        (
            datetime.datetime(2024, 7, 1, tzinfo=UTC),
            datetime.datetime(2024, 6, 1, tzinfo=UTC),
            False,
        ),
        (
            datetime.datetime(2024, 6, 1, tzinfo=UTC),
            datetime.datetime(2024, 6, 1, tzinfo=UTC),
            False,
        ),
    ],
)
def test_accepted_dotation_is_reopened_only_when_dossier_is_retour_en_instruction(
    date_traitement, date_passage_en_instruction, expected_back_to_instruction
):
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        date_programmation=datetime.datetime(2024, 4, 1, tzinfo=UTC),
        projet__dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION,
        projet__dossier_ds__ds_date_traitement=date_traitement,
        projet__dossier_ds__ds_date_passage_en_instruction=date_passage_en_instruction,
    )

    synchroniser(enveloppe_projet.projet)

    courant = enveloppe_projet.projet.enveloppeprojet_set.get()
    expected_status = (
        ProjetStatus.PROCESSING
        if expected_back_to_instruction
        else ProjetStatus.ACCEPTED
    )
    assert courant.status == expected_status


# -- montant of an accepted dotation --


@pytest.mark.django_db
def test_update_accepted_montant_from_dn_skips_non_accepted():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__annotations_montant_accorde_detr=2_000,
    )
    synchroniser(enveloppe_projet.projet)
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.montant is None


@pytest.mark.django_db
def test_update_accepted_montant_from_dn_updates_montant():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        montant=1_000,
        projet__dossier_ds__annotations_montant_accorde_detr=2_000,
    )
    synchroniser(enveloppe_projet.projet)
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.montant == 2_000


@pytest.mark.django_db
def test_update_accepted_montant_from_dn_does_not_update_montant_when_none():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        montant=1_000,
        projet__dossier_ds__annotations_montant_accorde_detr=None,
    )
    synchroniser(enveloppe_projet.projet)
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.montant == 1_000


@pytest.mark.django_db
def test_update_accepted_montant_from_dn_creates_action_when_montant_changes():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        montant=1_000,
        projet__dossier_ds__annotations_montant_accorde_detr=2_000,
    )

    synchroniser(enveloppe_projet.projet)

    actions = ProjetAction.objects.filter(
        projet=enveloppe_projet.projet,
        action_type=ProjetAction.TYPE_MONTANT_MODIFIED,
        dotation=DOTATION_DETR,
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.euro_field_value == 2_000
    assert action.source == ProjetAction.SOURCE_DN
    assert action.actor is None


@pytest.mark.django_db
def test_update_accepted_montant_from_dn_does_not_create_action_when_montant_unchanged():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        montant=1_000,
        projet__dossier_ds__annotations_montant_accorde_detr=1_000,
    )

    synchroniser(enveloppe_projet.projet)

    assert (
        ProjetAction.objects.filter(
            projet=enveloppe_projet.projet,
            action_type=ProjetAction.TYPE_MONTANT_MODIFIED,
        ).count()
        == 0
    )


# -- accepted dossier keeps the enveloppe of a programmed dotation --


@pytest.mark.django_db
def test_accept_enveloppe_projet_conserve_enveloppe_existante(perimetres):
    """
    Lors de la mise à jour d'un dossier accepté, si le enveloppe_projet est déjà programmé
    sur une enveloppe 2025, il ne doit pas être re-basculé sur l'enveloppe 2026.
    """
    arr_dijon, dep_21, *_ = perimetres
    enveloppe_2025 = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DetrEnveloppeFactory(perimetre=dep_21, annee=2026)

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.ACCEPTE,
        projet__dossier_ds__ds_date_traitement=datetime.datetime(
            2026, 3, 1, tzinfo=UTC
        ),
        projet__dossier_ds__annotations_dotation=DOTATION_DETR,
        projet__dossier_ds__annotations_montant_accorde_detr=5_000,
        enveloppe=enveloppe_2025,
        montant=4_000,
    )

    synchroniser(enveloppe_projet.projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe == enveloppe_2025

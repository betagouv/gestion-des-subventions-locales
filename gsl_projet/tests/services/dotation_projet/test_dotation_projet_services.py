import datetime
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
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
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
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

CURRENT_YEAR = datetime.datetime.now().year


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


# -- create_or_update_dotation_projet_from_projet --


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "dotation_value, dotation_projet_count",
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
def test_create_or_update_dotation_projet_from_projet(
    field,
    dotation_value,
    dotation_projet_count,
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=CURRENT_YEAR)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=CURRENT_YEAR)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_assiette_detr=1_000,
        dossier_ds__annotations_assiette_dsil=1_000,
        dossier_ds__perimetre=arr_dijon,
    )
    setattr(projet.dossier_ds, field, dotation_value)

    dps.create_or_update_dotation_projet_from_projet(projet)

    assert DotationProjet.objects.count() == dotation_projet_count

    for dotation_projet in DotationProjet.objects.all():
        assert dotation_projet.projet == projet
        assert dotation_projet.status == PROJET_STATUS_ACCEPTED
        assert dotation_projet.assiette == 1_000
        if dotation_projet.dotation == DOTATION_DSIL:
            assert dotation_projet.detr_avis_commission is None
        else:
            assert dotation_projet.detr_avis_commission is True


@pytest.mark.django_db
def test_create_or_update_dotation_projet_from_en_instruction_projet_ignore_annotations():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__annotations_dotation="DETR",
    )
    projet_dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    projet_dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert projet_dotation_projets.count() == 1

    dps.create_or_update_dotation_projet_from_projet(projet)

    projet_dotation_dsil.refresh_from_db()  # always exists

    projet_dotation_projets = DotationProjet.objects.filter(projet_id=projet.id)
    assert projet_dotation_projets.count() == 1

    dsil_dotation_projets = projet_dotation_projets.filter(dotation=DOTATION_DSIL)
    assert dsil_dotation_projets.count() == 1

    detr_dotation_projet = projet_dotation_projets.filter(dotation=DOTATION_DETR)
    assert detr_dotation_projet.count() == 0


@pytest.mark.django_db
def test_create_or_update_dotation_projet_from_projet_also_refuse_dsil_dotation_projet_even_if_not_in_demande_dispositif_sollicite(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=CURRENT_YEAR)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=CURRENT_YEAR)
    projet = ProjetFactory(
        dossier_ds__perimetre=arr_dijon,
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__demande_dispositif_sollicite="DETR",
    )
    projet_dotation_detr = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    projet_dotation_dsil = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
    )
    projet_dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert projet_dotation_projets.count() == 2

    dps.create_or_update_dotation_projet_from_projet(projet)

    projet_dotation_detr.refresh_from_db()  # always exists
    assert projet_dotation_detr.status == PROJET_STATUS_REFUSED

    projet_dotation_dsil.refresh_from_db()  # always exists
    assert projet_dotation_dsil.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
def test_create_or_update_dotation_projet_syncs_from_dn_when_dossier_updated_in_construction_detr_to_dsil(
    perimetres,
):
    """When _has_dotations_been_updated_on_dn returns True: projet has DETR, dossier has DSIL => one dotation-projet DSIL."""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
        dossier_ds__perimetre=arr_dijon,
    )
    assert projet.dotations_updated_in_app is False
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    dps.create_or_update_dotation_projet_from_projet(projet)

    dotation_projets = projet.dotationprojet_set.all()
    assert dotation_projets.count() == 1
    assert dotation_projets.first().dotation == DOTATION_DSIL


@pytest.mark.django_db
def test_create_or_update_dotation_projet_syncs_from_dn_when_dossier_updated_in_construction_dsil_to_detr_and_dsil(
    perimetres,
):
    """When _has_dotations_been_updated_on_dn returns True: projet has DSIL, dossier has DETR et DSIL => two dotation-projets DETR and DSIL."""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
        dossier_ds__perimetre=arr_dijon,
    )
    assert projet.dotations_updated_in_app is False
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    dps.create_or_update_dotation_projet_from_projet(projet)

    dotation_projets = projet.dotationprojet_set.all()
    assert dotation_projets.count() == 2
    assert set(projet.dotations) == {DOTATION_DETR, DOTATION_DSIL}


@pytest.mark.django_db
def test_create_or_update_dotation_projet_syncs_from_dn_when_dossier_updated_in_construction_detr_and_dsil_to_dsil(
    perimetres,
):
    """When _has_dotations_been_updated_on_dn returns True: projet has DETR and DSIL, dossier has DSIL => one dotation-projet DSIL."""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
        dossier_ds__perimetre=arr_dijon,
    )
    assert projet.dotations_updated_in_app is False
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    dps.create_or_update_dotation_projet_from_projet(projet)

    dotation_projets = projet.dotationprojet_set.all()
    assert dotation_projets.count() == 1
    assert dotation_projets.first().dotation == DOTATION_DSIL


# -- create_simulation_projets_from_dotation_projet --

# TODO category : useless now. Remove it if we don't allow to set DETR category.
# @pytest.mark.django_db
# @pytest.mark.parametrize(
#     "dotation",
#     (DOTATION_DETR, DOTATION_DSIL),
# )
# def test_create_or_update_dotation_projet_add_detr_categories(dotation):
#     projet = ProjetFactory(
#         dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
#     )
#     dotation_projet = DotationProjetFactory(
#         projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
#     )
#     categorie_detr = CategorieDetrFactory()
#     projet.dossier_ds.demande_eligibilite_detr.add(
#         CritereEligibiliteDetrFactory(detr_category=categorie_detr)
#     )

#     # ------

#     dps.create_or_update_dotation_projet_from_projet(projet)

#     # ------

#     assert DotationProjet.objects.count() == 1

#     dotation_projet = DotationProjet.objects.first()
#     assert dotation_projet.projet == projet
#     assert dotation_projet.dotation == dotation
#     assert dotation_projet.status == PROJET_STATUS_PROCESSING

#     if dotation_projet.dotation == DOTATION_DSIL:
#         assert dotation_projet.detr_categories.count() == 0
#     else:
#         assert categorie_detr in dotation_projet.detr_categories.all()


@pytest.fixture
def simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation(
    perimetres,
):
    arr_nanterre, dep_92, region_idf, arr_dijon, dep_21, region_bfc = perimetres
    for annee in [CURRENT_YEAR - 1, CURRENT_YEAR, 2026]:
        """
        Pour ces 3 années, on crée ces simulations :
        |--------------+-------+-------|
        | perimetre    | DETR  | DSIL  |
        |--------------+-------+-------|
        | reg_idf      |       |   x   |
        | dep_92       |   x   |   x   |
        | arr_nanterre |   x   |   x   |
        |--------------+-------+-------|
        | reg_bfc      |       |   x   |
        | dep_21       |   x   |   x   |
        | arr_dijon    |   x   |   x   |
        |--------------+-------+-------|
        """

        for perimetre in [
            arr_nanterre,
            dep_92,
            region_idf,
            arr_dijon,
            dep_21,
            region_bfc,
        ]:
            SimulationFactory(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DSIL,
                enveloppe__perimetre=perimetre,
            )

        for perimetre in [arr_nanterre, dep_92, arr_dijon, dep_21]:
            SimulationFactory(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DETR,
                enveloppe__perimetre=perimetre,
            )


@pytest.mark.django_db
def test_create_simulation_projets_from_dotation_projet_with_a_detr_and_arrondissement_projet(
    perimetres,
    simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation,
):
    arr_dijon, dep_21, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    dps.create_simulation_projets_from_dotation_projet(dotation_projet)

    # We only have a simulation_projets for enveloppe DETR of this year + the next year and on arr_dijon and dep_21 (because DETR)
    assert dotation_projet.simulationprojet_set.count() == 4
    for annee in [CURRENT_YEAR, 2026]:
        for perimetre in [dep_21, arr_dijon]:
            simulation = Simulation.objects.filter(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DETR,
                enveloppe__perimetre=perimetre,
            ).first()

            simulation_projets = SimulationProjet.objects.filter(
                simulation=simulation, dotation_projet=dotation_projet
            )
            assert simulation_projets.count() == 1

            simulation_projet = simulation_projets.first()
            assert simulation_projet.dotation_projet == dotation_projet
            assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
            assert simulation_projet.montant == 0
            assert simulation_projet.taux == 0

    last_year_simulation_projets = SimulationProjet.objects.filter(
        simulation__enveloppe__annee=CURRENT_YEAR - 1
    )
    assert last_year_simulation_projets.count() == 0


@pytest.mark.django_db
def test_create_simulation_projets_from_dotation_projet_with_a_dsil_and_departement_projet(
    perimetres,
    simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation,
):
    _, dep_21, region_bfc, *_ = perimetres
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=dep_21,
    )

    dps.create_simulation_projets_from_dotation_projet(dotation_projet)

    # We only have a simulation_projets for enveloppe DSIL of this year + the next year and on dep_21 and region_bfc
    assert dotation_projet.simulationprojet_set.count() == 4
    for annee in [CURRENT_YEAR, 2026]:
        for perimetre in [region_bfc, dep_21]:
            simulation = Simulation.objects.filter(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DSIL,
                enveloppe__perimetre=perimetre,
            ).first()

            simulation_projets = SimulationProjet.objects.filter(
                simulation=simulation, dotation_projet=dotation_projet
            )
            assert simulation_projets.count() == 1

            simulation_projet = simulation_projets.first()
            assert simulation_projet.dotation_projet == dotation_projet
            assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
            assert simulation_projet.montant == 0
            assert simulation_projet.taux == 0

    last_year_simulation_projets = SimulationProjet.objects.filter(
        simulation__enveloppe__annee=CURRENT_YEAR - 1
    )
    assert last_year_simulation_projets.count() == 0


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize(
    "dossier_state",
    (
        Dossier.STATE_ACCEPTE,
        Dossier.STATE_EN_CONSTRUCTION,
        Dossier.STATE_EN_INSTRUCTION,
        Dossier.STATE_REFUSE,
        Dossier.STATE_SANS_SUITE,
    ),
)
@pytest.mark.django_db
def test_get_detr_avis_commission(dotation, dossier_state):
    dossier = DossierFactory(
        ds_state=dossier_state,
    )
    avis_commissioin_detr = dps._get_detr_avis_commission(dotation, dossier)
    if dotation == DOTATION_DETR and dossier_state == Dossier.STATE_ACCEPTE:
        assert avis_commissioin_detr is True
    else:
        assert avis_commissioin_detr is None


# -- _should_dotations_be_updated_from_dn_construction_dossier --


@pytest.mark.django_db
def test_has_dotations_been_updated_on_dn_returns_false_when_updated_in_app():
    """Returns False when dotations have been updated in Turgot (we don't sync from DN)."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
        dotations_updated_in_app=True,
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert (
        dps._should_dotations_be_updated_from_dn_construction_dossier(projet) is False
    )


@pytest.mark.django_db
def test_has_dotations_been_updated_on_dn_returns_false_when_not_en_construction():
    """Returns False when dossier is not in EN_CONSTRUCTION state."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert (
        dps._should_dotations_be_updated_from_dn_construction_dossier(projet) is False
    )


@pytest.mark.django_db
def test_has_dotations_been_updated_on_dn_returns_true_when_projet_has_dotation_not_in_dossier():
    """Returns True when projet has a dotation not in demande_dispositif_sollicite."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert dps._should_dotations_be_updated_from_dn_construction_dossier(projet) is True


@pytest.mark.django_db
def test_has_dotations_been_updated_on_dn_returns_true_when_dossier_has_dotation_not_in_projet():
    """Returns True when dossier has a dotation not in projet (e.g. user added DSIL on DN)."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert dps._should_dotations_be_updated_from_dn_construction_dossier(projet) is True


@pytest.mark.django_db
def test_has_dotations_been_updated_on_dn_returns_false_when_dotations_match():
    """Returns False when projet and dossier have the same dotations."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR']",
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert (
        dps._should_dotations_be_updated_from_dn_construction_dossier(projet) is False
    )


@pytest.mark.django_db
def test_has_dotations_been_updated_on_dn_returns_false_when_both_have_detr_and_dsil():
    """Returns False when both projet and dossier have DETR and DSIL."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    assert (
        dps._should_dotations_be_updated_from_dn_construction_dossier(projet) is False
    )


# -- _remove_or_add_dotations_from_dossier_ds --


@pytest.mark.django_db
def test_remove_or_add_dotations_removes_dotation_not_in_dossier():
    """Removes dotation_projet when projet has dotation not in demande_dispositif_sollicite."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
    )
    detr_dp = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dsil_dp = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    dps._remove_or_add_dotations_from_dossier_ds(projet)

    assert not DotationProjet.objects.filter(pk=detr_dp.pk).exists()
    assert DotationProjet.objects.filter(pk=dsil_dp.pk).exists()
    assert projet.dotations == [DOTATION_DSIL]


@pytest.mark.django_db
def test_remove_or_add_dotations_adds_dotation_from_dossier():
    """Adds dotation_projet when dossier has dotation not in projet."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    dps._remove_or_add_dotations_from_dossier_ds(projet)

    assert projet.dotationprojet_set.count() == 2
    assert set(projet.dotations) == {DOTATION_DETR, DOTATION_DSIL}


@pytest.mark.django_db
def test_remove_or_add_dotations_removes_and_adds_when_differing():
    """Removes and adds dotations when projet and dossier have different dotations."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DSIL']",
    )
    detr_dp = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    dps._remove_or_add_dotations_from_dossier_ds(projet)

    assert not DotationProjet.objects.filter(pk=detr_dp.pk).exists()
    assert projet.dotationprojet_set.count() == 1
    assert projet.dotations == [DOTATION_DSIL]


@pytest.mark.django_db
def test_remove_or_add_dotations_does_nothing_when_matching():
    """Does nothing when projet and dossier have the same dotations."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR']",
    )
    detr_dp = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    dps._remove_or_add_dotations_from_dossier_ds(projet)

    assert DotationProjet.objects.filter(pk=detr_dp.pk).exists()
    assert projet.dotations == [DOTATION_DETR]


@pytest.mark.django_db
def test_remove_or_add_dotations_creates_dotation_projet_with_assiette_from_dossier():
    """New dotation_projet gets assiette from dossier annotations when available."""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="['DETR', 'DSIL']",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    dps._remove_or_add_dotations_from_dossier_ds(projet)

    dsil_dp = projet.dotationprojet_set.get(dotation=DOTATION_DSIL)
    assert dsil_dp.assiette == 20_000


# -- _update_assiette_from_dossier --


@pytest.mark.django_db
def test_update_assiette_from_dossier_single_detr():
    """Updates DETR dotation_projet assiette from dossier annotations_assiette_detr."""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=15_000,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, assiette=0
    )

    dps._update_assiette_from_dossier(projet)

    dotation_projet.refresh_from_db()
    assert dotation_projet.assiette == 15_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_single_dsil():
    """Updates DSIL dotation_projet assiette from dossier annotations_assiette_dsil."""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=15_000,
        dossier_ds__annotations_assiette_dsil=25_000,
    )
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, assiette=0
    )

    dps._update_assiette_from_dossier(projet)

    dotation_projet.refresh_from_db()
    assert dotation_projet.assiette == 25_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_both_dotations():
    """Updates both DETR and DSIL dotation_projets with correct dossier values."""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=30_000,
    )
    dp_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, assiette=0)
    dp_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL, assiette=0)

    dps._update_assiette_from_dossier(projet)

    dp_detr.refresh_from_db()
    dp_dsil.refresh_from_db()
    assert dp_detr.assiette == 10_000
    assert dp_dsil.assiette == 30_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_keeps_existing_assiette_when_missing_in_dossier():
    """Keeps existing assiette when dossier has no annotation for that dotation."""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, assiette=5_000
    )

    dps._update_assiette_from_dossier(projet)

    dotation_projet.refresh_from_db()
    assert dotation_projet.assiette == 5_000


@pytest.mark.django_db
def test_update_assiette_from_dossier_no_dotation_projets():
    """Does nothing when projet has no dotation_projets (no error)."""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=20_000,
    )
    assert projet.dotationprojet_set.count() == 0

    dps._update_assiette_from_dossier(projet)

    assert projet.dotationprojet_set.count() == 0


# -- _get_simulation_concerning_by_this_dotation_projet --


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_filters_by_perimetre(
    perimetres,
):
    """Test that the function returns simulations containing the projet's perimetre."""
    arr_dijon, dep_21, region_bfc, arr_nanterre, dep_92, region_idf = perimetres

    # Create a projet with arrondissement perimetre
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    # Create simulations with different perimetres
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    # Should include simulations with arr_dijon and dep_21 (ancestor)
    assert sim_arr_dijon in results
    assert sim_dep_21 in results
    # Should not include simulation with different perimetre
    assert sim_arr_nanterre not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_filters_by_dotation(
    perimetres,
):
    """Test that the function only returns simulations with matching dotation."""
    arr_dijon, dep_21, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    # Create simulations with different dotations
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert sim_detr in results
    assert sim_dsil not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_filters_by_year(
    perimetres,
):
    """Test that the function only returns simulations with year >= current year."""
    arr_dijon, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    # Create simulations with different years
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert sim_current_year in results
    assert sim_next_year in results
    assert sim_previous_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_excludes_existing_simulation_projet(
    perimetres,
):
    """Test that the function excludes simulations that already have a SimulationProjet for this dotation_projet."""
    arr_dijon, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    # Create simulations
    sim_with_existing = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    sim_without_existing = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    # Create a SimulationProjet for one simulation
    SimulationProjetFactory(
        simulation=sim_with_existing,
        dotation_projet=dotation_projet,
    )

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert sim_with_existing not in results
    assert sim_without_existing in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_with_department_perimetre(
    perimetres,
):
    """Test that the function works correctly with department-level perimetres."""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        projet__dossier_ds__perimetre=dep_21,
    )

    # Create simulations
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    # Should include both department and region (ancestor)
    assert sim_dep_21 in results
    assert sim_region_bfc in results

    # Should not include arrondissement
    assert sim_arr_dijon not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_with_region_perimetre(
    perimetres,
):
    """Test that the function works correctly with region-level perimetres."""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        projet__dossier_ds__perimetre=region_bfc,
    )

    # Create simulations
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    # Only region should be included
    assert sim_region_bfc in results

    assert sim_arr_dijon not in results
    assert sim_dep_21 not in results
    assert sim_region_idf not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_combines_all_filters(
    perimetres,
):
    """Test that the function correctly combines all filters."""
    arr_dijon, dep_21, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )

    # Create a simulation that matches all criteria
    sim_valid = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )

    # Create simulations that fail different criteria
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
    sim_existing = SimulationFactory(
        enveloppe__perimetre=arr_dijon,
        enveloppe__dotation=DOTATION_DETR,
        enveloppe__annee=CURRENT_YEAR,
    )
    SimulationProjetFactory(
        simulation=sim_existing,
        dotation_projet=dotation_projet,
    )

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert sim_valid in results
    assert sim_wrong_dotation not in results
    assert sim_wrong_year not in results
    # sim_dep_perimetre should be included since dep_21 is an ancestor of arr_dijon
    # and containing_perimetre includes ancestors
    assert sim_dep_perimetre in results
    assert sim_existing not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "dossier_state",
    [Dossier.STATE_ACCEPTE, Dossier.STATE_SANS_SUITE, Dossier.STATE_REFUSE],
)
def test_get_simulation_concerning_by_this_dotation_projet_excludes_future_years_for_terminal_state_with_treatment_date(
    perimetres, dossier_state
):
    """Test that the function excludes simulations for years >= (treatment_year + 1) when dossier is in terminal state with treatment date."""
    arr_dijon, *_ = perimetres
    last_year = CURRENT_YEAR - 1

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=dossier_state,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            last_year, 6, 15, tzinfo=UTC
        ),
    )

    # Create simulations with different years
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert results.count() == 0, (
        "Should not include any simulations, because the dossier has been treated in the last year"
    )


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_does_not_exclude_when_terminal_state_without_treatment_date(
    perimetres,
):
    """Test that the function does not exclude future years when dossier is in terminal state but has no treatment date."""
    arr_dijon, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        projet__dossier_ds__ds_date_traitement=None,
    )

    # Create simulations with different years
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)
    assert results.count() == 2, (
        "Should include all future years since there's no treatment date"
    )

    # Should include all future years since there's no treatment date
    assert sim_current_year in results
    assert sim_next_year in results

    # Should not include last year
    assert sim_last_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_does_not_exclude_when_not_terminal_state(
    perimetres,
):
    """Test that the function does not exclude future years when dossier is not in terminal state."""
    arr_dijon, *_ = perimetres
    treatment_year = CURRENT_YEAR - 1

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            treatment_year, 6, 15, tzinfo=UTC
        ),
    )

    # Create simulations with different years
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert results.count() == 2, (
        "Should include all future years since dossier is not in terminal state"
    )

    # Should include all future years since dossier is not in terminal state
    assert sim_current_year in results
    assert sim_next_year in results

    # Should not include last year
    assert sim_last_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_excludes_correctly_when_treatment_year_is_current_year(
    perimetres,
):
    """Test that the function correctly excludes when treatment year is current year."""
    arr_dijon, *_ = perimetres
    treatment_year = CURRENT_YEAR

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            treatment_year, 6, 15, tzinfo=UTC
        ),
    )

    # Create simulations with different years
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert results.count() == 1, (
        "Should include only current year since treatment year is current year"
    )

    # Should include current year (treatment_year)
    assert sim_current_year in results
    # Should exclude years >= treatment_year + 1
    assert sim_next_year not in results


# -- _is_dossier_back_to_instruction --


@pytest.mark.django_db
@pytest.mark.parametrize(
    "date_traitement, date_passage_en_instruction, expected",
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
def test_is_dossier_back_to_instruction(
    date_traitement, date_passage_en_instruction, expected
):
    projet = ProjetFactory(
        dossier_ds__ds_date_traitement=date_traitement,
        dossier_ds__ds_date_passage_en_instruction=date_passage_en_instruction,
    )
    assert dps._is_dossier_back_to_instruction(projet) is expected


# -- _update_accepted_dotation_projets_montant_from_dn --


@pytest.mark.django_db
def test_update_accepted_dotation_projets_montant_from_dn_skips_non_accepted():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__annotations_montant_accorde_detr=2_000,
    )
    pp = ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=1_000)
    dps._update_accepted_dotation_projets_montant_from_dn(dotation_projet.projet)
    pp.refresh_from_db()
    assert pp.montant == 1_000


@pytest.mark.django_db
def test_update_accepted_dotation_projets_montant_from_dn_updates_montant():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__annotations_montant_accorde_detr=2_000,
    )
    pp = ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=1_000)
    dps._update_accepted_dotation_projets_montant_from_dn(dotation_projet.projet)
    pp.refresh_from_db()
    assert pp.montant == 2_000


@pytest.mark.django_db
def test_update_accepted_dotation_projets_montant_from_dn_does_not_update_montant_when_none():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__annotations_montant_accorde_detr=None,
    )
    pp = ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=1_000)
    dps._update_accepted_dotation_projets_montant_from_dn(dotation_projet.projet)
    pp.refresh_from_db()
    assert pp.montant == 1_000


@pytest.mark.django_db
def test_update_accepted_dotation_projets_montant_from_dn_does_not_update_montant_without_pp():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__annotations_montant_accorde_detr=2_000,
    )
    dps._update_accepted_dotation_projets_montant_from_dn(dotation_projet.projet)
    assert not ProgrammationProjet.objects.filter(
        dotation_projet=dotation_projet
    ).exists()


# -- _accept_dotation_projet --


@pytest.mark.django_db
def test_accept_dotation_projet_conserve_enveloppe_existante(perimetres):
    """
    Lors de la mise à jour d'un dossier accepté, si le dotation_projet est déjà programmé
    sur une enveloppe 2025, il ne doit pas être re-basculé sur l'enveloppe 2026.
    """
    arr_dijon, dep_21, *_ = perimetres
    enveloppe_2025 = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DetrEnveloppeFactory(perimetre=dep_21, annee=2026)

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        projet__dossier_ds__ds_date_traitement=datetime.datetime(
            2026, 3, 1, tzinfo=UTC
        ),
        projet__dossier_ds__annotations_dotation=DOTATION_DETR,
        projet__dossier_ds__annotations_montant_accorde_detr=5_000,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        enveloppe=enveloppe_2025,
        montant=4_000,
    )

    dps._accept_dotation_projet(dotation_projet.projet, DOTATION_DETR)

    dotation_projet.refresh_from_db()
    assert dotation_projet.programmation_projet.enveloppe == enveloppe_2025


# -- _get_simulation_concerning_by_this_dotation_projet (programmation_projet) --


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_excludes_simulations_after_programmation_year(
    perimetres,
):
    """Test que les simulations dont l'année > année enveloppe de la programmation sont exclues."""
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_current_year = DetrEnveloppeFactory(
        perimetre=dep_21,
        annee=CURRENT_YEAR,
    )
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        projet__dossier_ds__perimetre=arr_dijon,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert sim_current_year in results
    assert sim_next_year not in results


@freeze_time(f"{CURRENT_YEAR}-05-06")
@pytest.mark.django_db
def test_get_simulation_concerning_by_this_dotation_projet_includes_all_years_when_no_programmation(
    perimetres,
):
    """Test que toutes les années >= année courante sont incluses sans programmation_projet."""
    arr_dijon, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
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

    results = dps._get_simulation_concerning_by_this_dotation_projet(dotation_projet)

    assert sim_current_year in results
    assert sim_next_year in results

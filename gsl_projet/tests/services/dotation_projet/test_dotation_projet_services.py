import datetime
import re
from decimal import Decimal

import pytest
from freezegun import freeze_time

from gsl_core.templatetags.gsl_filters import euro, percent
from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    CritereEligibiliteDetrFactory,
    DossierFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
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
    CategorieDetrFactory,
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
        perimetre=arr_dijon,
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
        perimetre=arr_dijon,
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


# -- create_simulation_projets_from_dotation_projet --


@pytest.mark.django_db
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DETR, DOTATION_DSIL),
)
def test_create_or_update_dotation_projet_add_detr_categories(dotation):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
    )
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )
    categorie_detr = CategorieDetrFactory()
    projet.dossier_ds.demande_eligibilite_detr.add(
        CritereEligibiliteDetrFactory(detr_category=categorie_detr)
    )

    # ------

    dps.create_or_update_dotation_projet_from_projet(projet)

    # ------

    assert DotationProjet.objects.count() == 1

    dotation_projet = DotationProjet.objects.first()
    assert dotation_projet.projet == projet
    assert dotation_projet.dotation == dotation
    assert dotation_projet.status == PROJET_STATUS_PROCESSING

    if dotation_projet.dotation == DOTATION_DSIL:
        assert dotation_projet.detr_categories.count() == 0
    else:
        assert categorie_detr in dotation_projet.detr_categories.all()


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
        projet__perimetre=arr_dijon,
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
        projet__perimetre=dep_21,
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


@pytest.mark.parametrize("field", ("assiette", "finance_cout_total"))
@pytest.mark.parametrize(
    "montant, assiette_or_cout_total, should_raise_exception",
    [
        (50, 100, False),  # Valid montant
        (0, 100, False),  # Valid montant at lower bound
        (100, 100, False),  # Valid montant at upper bound
        (-1, 100, True),  # Invalid montant below lower bound
        (101, 100, True),  # Invalid montant above upper bound
        (None, 100, True),  # Invalid montant as None
        ("invalid", 100, True),  # Invalid montant as string
    ],
)
@pytest.mark.django_db
def test_validate_montant(
    field, montant, assiette_or_cout_total, should_raise_exception
):
    dotation_projet = DotationProjetFactory()
    if field == "finance_cout_total":
        dotation_projet.projet.dossier_ds.finance_cout_total = assiette_or_cout_total
    else:
        dotation_projet.assiette = assiette_or_cout_total

    if should_raise_exception:
        with pytest.raises(
            ValueError,
            match=(
                re.escape(
                    f"Le montant {euro(montant)} doit être supérieur ou égal à 0 € et inférieur ou "
                    f"égal à l'assiette ({euro(dotation_projet.assiette_or_cout_total)})."
                )
            ),
        ):
            dps.validate_montant(montant, dotation_projet)

    else:
        dps.validate_montant(montant, dotation_projet)


# -- compute_montant_from_taux --


@pytest.mark.django_db
def test_compute_montant_from_taux():
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
    )
    taux = dps.compute_montant_from_taux(dotation_projet, 25)
    assert taux == 25_000

    dotation_projet = DotationProjetFactory(
        assiette=50_000,
    )
    taux = dps.compute_montant_from_taux(dotation_projet, 25)
    assert taux == 12_500

    dotation_projet = DotationProjetFactory()
    taux = dps.compute_montant_from_taux(dotation_projet, 25)
    assert taux == 0


test_data = (
    (30_000, 33.333, 9_999.90),
    (10_000, 100, 10_000),
    (10_000, 1000, 10_000),
    (-3_000, 10, 0),
    (0, 100, 0),
    (0, 0, 0),
    (Decimal(0), 0, 0),
    (1_000, Decimal(10), 100),
    (None, 0, 0),
    (None, 10, 0),
    (0, None, 0),
    (10, None, 0),
    (4_000, 0, 0),
)


@pytest.mark.parametrize("assiette, taux, expected_montant", test_data)
@pytest.mark.django_db
def test_compute_montant_from_taux_with_various_assiettes(
    assiette, taux, expected_montant
):
    dotation_projet = DotationProjetFactory(assiette=assiette)
    montant = dps.compute_montant_from_taux(dotation_projet, taux)
    assert montant == round(Decimal(expected_montant), 2)


@pytest.mark.parametrize("cout_total, taux, expected_montant", test_data)
@pytest.mark.django_db
def test_compute_montant_from_taux_with_various_cout_total(
    taux, cout_total, expected_montant
):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=cout_total
    )
    montant = dps.compute_montant_from_taux(dotation_projet, taux)
    assert montant == round(Decimal(expected_montant), 2)


# -- validate_taux --


@pytest.mark.parametrize(
    "taux, should_raise_exception",
    [
        (50, False),
        (0, False),
        (100, False),
        (-1, True),
        (101, True),
        (None, True),
        ("invalid", True),
    ],
)
def test_validate_taux(taux, should_raise_exception):
    if should_raise_exception:
        with pytest.raises(
            ValueError, match=f"Le taux {percent(taux)} doit être entre 0% and 100%"
        ):
            dps.validate_taux(taux)
    else:
        dps.validate_taux(taux)


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
        projet__perimetre=arr_dijon,
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
        projet__perimetre=arr_dijon,
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
        projet__perimetre=arr_dijon,
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
        projet__perimetre=arr_dijon,
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
        projet__perimetre=dep_21,
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
        projet__perimetre=region_bfc,
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
        projet__perimetre=arr_dijon,
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
    sim_wrong_perimetre = SimulationFactory(
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
    # sim_wrong_perimetre should be included since dep_21 is an ancestor of arr_dijon
    # and containing_perimetre includes ancestors
    assert sim_wrong_perimetre in results
    assert sim_existing not in results

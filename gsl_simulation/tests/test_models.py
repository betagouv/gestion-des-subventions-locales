from decimal import Decimal

import pytest
from django.forms import ValidationError

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.mark.parametrize(
    "montant, assiette, finance_cout_total, expected_taux",
    (
        (1_000, 2_000, 4_000, 50),
        (1_000, 2_000, None, 50),
        (1_000, None, 4_000, 25),
        (1_000, None, None, 0),
    ),
)
@pytest.mark.django_db
def test_progammation_projet_taux(montant, assiette, finance_cout_total, expected_taux):
    dotation_projet = DotationProjetFactory(
        assiette=assiette, projet__dossier_ds__finance_cout_total=finance_cout_total
    )
    programmation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet, montant=montant
    )
    assert isinstance(programmation_projet.taux, Decimal)
    assert programmation_projet.taux == expected_taux


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def simulation_projects(simulation):
    SimulationProjetFactory.create_batch(
        2,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory(
        status=SimulationProjet.STATUS_ACCEPTED,
        dotation_projet__dotation=simulation.enveloppe.dotation,
    )
    SimulationProjetFactory.create_batch(
        3,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_REFUSED,
    )
    SimulationProjetFactory.create_batch(
        1,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_PROCESSING,
    )
    SimulationProjetFactory.create_batch(
        4,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
    )


@pytest.mark.django_db
def test_get_projet_status_summary(simulation, simulation_projects):
    summary = simulation.get_projet_status_summary()

    expected_summary = {
        SimulationProjet.STATUS_REFUSED: 3,
        SimulationProjet.STATUS_PROCESSING: 1,
        SimulationProjet.STATUS_ACCEPTED: 2,
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: 0,
        SimulationProjet.STATUS_PROVISIONALLY_REFUSED: 4,
        "notified": 0,
    }

    assert summary == expected_summary


@pytest.mark.django_db
def test_simulation_projet_cant_have_a_montant_higher_than_projet_assiette():
    dotation_projet = DotationProjetFactory(
        assiette=100, projet__dossier_ds__finance_cout_total=200
    )
    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(dotation_projet=dotation_projet, montant=101)
        assert sp.montant == 101
        sp.save()
    assert (
        "Le montant de la simulation ne peut pas être supérieur à l'assiette du projet"
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_simulation_projet_cant_have_a_montant_higher_than_projet_cout_total():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        assiette=None,
        projet__dossier_ds__finance_cout_total=100,
    )
    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            montant=101,
        )
        sp.save()
    assert (
        "Le montant de la simulation ne peut pas être supérieur au coût total du projet"
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_simulation_projet_must_have_a_dotation_consistency():
    dotation_projet = DotationProjetFactory(dotation=DOTATION_DSIL)
    simulation = SimulationFactory(enveloppe__dotation=DOTATION_DETR)

    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(
            simulation=simulation,
            dotation_projet=dotation_projet,
        )
        sp.save()
    assert (
        "La dotation du projet doit être la même que la dotation de la simulation."
        in exc_info.value.message_dict.get("dotation_projet")[0]
    )


# Tests for containing_perimetre


@pytest.mark.django_db
def test_containing_perimetre_with_region_includes_all_children():
    """Test that filtering by a region perimetre includes simulations with
    enveloppes in that region, its departments, and arrondissements."""
    # Create a hierarchy: region -> department -> arrondissement
    arrondissement = PerimetreArrondissementFactory()
    departement = PerimetreDepartementalFactory(
        departement=arrondissement.departement, region=arrondissement.region
    )
    region = PerimetreRegionalFactory(region=arrondissement.region)

    # Create another region to test exclusion
    other_region = PerimetreRegionalFactory()

    # Create simulations with enveloppes at different levels
    # Note: DSIL enveloppes can have region perimetres, DETR cannot
    sim_regional = SimulationFactory(enveloppe=DsilEnveloppeFactory(perimetre=region))
    sim_departemental = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=departement)
    )
    sim_arrondissement = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=arrondissement)
    )
    sim_other_region = SimulationFactory(
        enveloppe=DsilEnveloppeFactory(perimetre=other_region)
    )

    # Filter by region
    results = Simulation.objects.containing_perimetre(region)

    # Should only include simulations in the region hierarchy
    assert sim_regional in results

    # Should not include simulation with a smaller perimeter
    assert sim_departemental not in results
    assert sim_arrondissement not in results

    # Should not include simulations from other regions
    assert sim_other_region not in results

    assert results.count() == 1


@pytest.mark.django_db
def test_containing_perimetre_with_departement_includes_department_and_arrondissements():
    """Test that filtering by a department perimetre includes simulations with
    enveloppes in that department and its arrondissements, but not other departments."""
    # Create a hierarchy: region -> department1, department2 -> arrondissement1, arrondissement2
    arrondissement1 = PerimetreArrondissementFactory()
    departement1 = PerimetreDepartementalFactory(
        departement=arrondissement1.departement, region=arrondissement1.region
    )
    region = PerimetreRegionalFactory(region=arrondissement1.region)

    # Create another department in the same region
    departement2 = PerimetreDepartementalFactory(
        departement__region=region.region, region=region.region
    )
    arrondissement2 = PerimetreArrondissementFactory(
        arrondissement__departement=departement2.departement,
        departement=departement2.departement,
        region=region.region,
    )

    # Create simulations
    sim_departement1 = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=departement1)
    )
    sim_arrondissement1 = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=arrondissement1)
    )
    sim_departement2 = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=departement2)
    )
    sim_arrondissement2 = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=arrondissement2)
    )
    sim_regional = SimulationFactory(enveloppe=DsilEnveloppeFactory(perimetre=region))

    # Filter by department1
    results = Simulation.objects.containing_perimetre(departement1)

    # Should include department1 and its region
    assert sim_departement1 in results
    assert sim_regional in results

    # Should not include department1 arrondissement, department2 or its arrondissement
    assert sim_arrondissement1 not in results
    assert sim_departement2 not in results
    assert sim_arrondissement2 not in results

    assert results.count() == 2


@pytest.mark.django_db
def test_containing_perimetre_with_arrondissement_includes_only_that_arrondissement():
    """Test that filtering by an arrondissement perimetre includes only
    simulations with enveloppes in that specific arrondissement."""
    # Create a hierarchy: region -> department -> arrondissement1, arrondissement2
    arrondissement1 = PerimetreArrondissementFactory()
    arrondissement2 = PerimetreArrondissementFactory(
        arrondissement__departement=arrondissement1.departement,
        departement=arrondissement1.departement,
        region=arrondissement1.region,
    )
    departement = PerimetreDepartementalFactory(
        departement=arrondissement1.departement, region=arrondissement1.region
    )
    region = PerimetreRegionalFactory(region=arrondissement1.region)

    # Create simulations
    sim_arrondissement1 = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=arrondissement1)
    )
    sim_arrondissement2 = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=arrondissement2)
    )
    sim_departement = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=departement)
    )
    sim_regional = SimulationFactory(enveloppe=DsilEnveloppeFactory(perimetre=region))

    # Filter by arrondissement1
    results = Simulation.objects.containing_perimetre(arrondissement1)

    # Should include only arrondissement1, department and region
    assert sim_arrondissement1 in results
    assert sim_departement in results
    assert sim_regional in results

    # Should not include arrondissement2
    assert sim_arrondissement2 not in results

    assert results.count() == 3


@pytest.mark.django_db
def test_containing_perimetre_with_no_matching_simulations():
    """Test that filtering by a perimetre with no matching simulations returns empty queryset."""
    perimetre = PerimetreDepartementalFactory()

    # No simulations created for this perimetre
    results = Simulation.objects.containing_perimetre(perimetre)

    assert results.count() == 0
    assert list(results) == []


@pytest.mark.django_db
def test_containing_perimetre_includes_exact_match():
    """Test that filtering includes simulations with enveloppes matching the exact perimetre."""
    perimetre = PerimetreDepartementalFactory()
    sim_exact = SimulationFactory(enveloppe=DetrEnveloppeFactory(perimetre=perimetre))

    results = Simulation.objects.containing_perimetre(perimetre)

    assert sim_exact in results
    assert results.count() == 1

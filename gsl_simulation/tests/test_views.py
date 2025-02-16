from datetime import UTC, datetime

import pytest
from django.urls import resolve, reverse

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
    RequestFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
)
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DemandeurFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tasks import add_enveloppe_projets_to_simulation
from gsl_simulation.tests.factories import SimulationFactory
from gsl_simulation.views import SimulationDetailView, SimulationListView

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def req(perimetre_departemental) -> RequestFactory:
    user = CollegueFactory(perimetre=perimetre_departemental)
    return RequestFactory(user=user)


@pytest.fixture
def view() -> SimulationListView:
    return SimulationListView()


@pytest.fixture
def simulations(perimetre_departemental):
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre_departemental)
    SimulationFactory(enveloppe=enveloppe)
    SimulationFactory(enveloppe=enveloppe)
    SimulationFactory()


@pytest.fixture
def simulation(perimetre_departemental):
    enveloppe = DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2024, montant=1_000_000
    )
    return SimulationFactory(enveloppe=enveloppe)


@pytest.fixture
def projets(simulation, perimetre_departemental):
    other_perimeter = PerimetreDepartementalFactory()
    projets = []
    epci = NaturePorteurProjetFactory(label="EPCI")
    commune = NaturePorteurProjetFactory(label="Commune")

    for perimetre in [perimetre_departemental, other_perimeter]:
        for type in ("DETR", "DSIL"):
            demandeur = DemandeurFactory(departement=perimetre.departement)
            for state in (
                Dossier.STATE_ACCEPTE,
                Dossier.STATE_REFUSE,
                Dossier.STATE_SANS_SUITE,
            ):
                dossier_2024 = DossierFactory(
                    ds_state=state,
                    ds_date_depot=datetime(2023, 10, 1, tzinfo=UTC),
                    ds_date_traitement=datetime(2024, 1, 1, tzinfo=UTC),
                    annotations_montant_accorde=150_000,
                    demande_montant=200_000,
                    demande_dispositif_sollicite=type,
                    finance_cout_total=1_000_000,
                    porteur_de_projet_nature=epci,
                )
                projet_2024 = ProjetFactory(
                    dossier_ds=dossier_2024, demandeur=demandeur
                )
                projets.append(projet_2024)

                dossier_2025 = DossierFactory(
                    ds_state=state,
                    ds_date_traitement=datetime(2025, 1, 1, tzinfo=UTC),
                    demande_montant=300_000,
                    annotations_montant_accorde=120_000,
                    demande_dispositif_sollicite=type,
                    finance_cout_total=2_000_000,
                    porteur_de_projet_nature=commune,
                )
                projet_2025 = ProjetFactory(
                    dossier_ds=dossier_2025, demandeur=demandeur
                )
                projets.append(projet_2025)

            demandeur = DemandeurFactory(departement=perimetre.departement)
            for state in (Dossier.STATE_EN_CONSTRUCTION, Dossier.STATE_EN_INSTRUCTION):
                dossier_2024 = DossierFactory(
                    ds_state=state,
                    ds_date_depot=datetime(2024, 2, 12, tzinfo=UTC),
                    ds_date_traitement=None,
                    demande_dispositif_sollicite=type,
                    demande_montant=400_000,
                    finance_cout_total=3_000_000,
                    porteur_de_projet_nature=commune,
                )
                projet_2024 = ProjetFactory(
                    dossier_ds=dossier_2024, demandeur=demandeur
                )
                projets.append(projet_2024)

                dossier_2025 = DossierFactory(
                    ds_state=state,
                    ds_date_depot=datetime(2025, 2, 12, tzinfo=UTC),
                    ds_date_traitement=None,
                    demande_dispositif_sollicite=type,
                    demande_montant=500_000,
                    finance_cout_total=4_000_000,
                    porteur_de_projet_nature=epci,
                )
                projet_2025 = ProjetFactory(
                    dossier_ds=dossier_2025, demandeur=demandeur
                )
                projets.append(projet_2025)
    return projets


@pytest.mark.django_db
def test_simulation_view_status_code(req, view, simulations):
    url = reverse("simulation:simulation-list")
    view.object_list = simulations
    view.request = req.get(url)

    assert view.get_queryset().count() == 2
    assert (
        view.get_queryset().first().created_at > view.get_queryset().last().created_at
    )


@pytest.mark.django_db
def test_get_enveloppe_data(req, simulation, projets, perimetre_departemental):
    view = SimulationDetailView()
    view.kwargs = {"slug": simulation.slug}
    view.request = req.get(
        reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
    )
    view.object = simulation
    enveloppe_data = view._get_enveloppe_data(simulation)

    assert Projet.objects.count() == 40

    projet_filter_by_perimetre = Projet.objects.for_perimetre(perimetre_departemental)
    assert projet_filter_by_perimetre.count() == 20

    projet_filter_by_perimetre_and_type = projet_filter_by_perimetre.filter(
        dossier_ds__demande_dispositif_sollicite="DETR"
    )
    assert projet_filter_by_perimetre_and_type.count() == 10

    projet_qs_submitted_before_the_end_of_the_year = (
        projet_filter_by_perimetre_and_type.filter(
            dossier_ds__ds_date_depot__lt=datetime(
                simulation.enveloppe.annee + 1, 1, 1, tzinfo=UTC
            ),
        )
    )
    assert projet_qs_submitted_before_the_end_of_the_year.count() == 5

    assert enveloppe_data["type"] == "DETR"
    assert enveloppe_data["montant"] == 1_000_000
    assert enveloppe_data["perimetre"] == perimetre_departemental
    assert enveloppe_data["validated_projets_count"] == 1
    assert enveloppe_data["refused_projets_count"] == 1
    assert enveloppe_data["projets_count"] == 5
    assert enveloppe_data["demandeurs"] == 2
    assert enveloppe_data["montant_asked"] == 200_000 * 3 + 400_000 * 2
    assert enveloppe_data["montant_accepte"] == 150_000


@pytest.fixture
def create_simulation_projets(simulation, projets):
    add_enveloppe_projets_to_simulation(simulation.id)


def _get_view_with_filter(req, simulation, filter_params):
    url = reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
    request = req.get(url, data=filter_params)
    request.resolver_match = resolve(url)

    view = SimulationDetailView()
    view.object = simulation

    view.request = request
    view.kwargs = {"slug": simulation.slug}
    return view


def test_view_without_filter(req, simulation, create_simulation_projets):
    view = _get_view_with_filter(req, simulation, {})
    projets = view.get_projet_queryset()
    assert projets.count() == 7
    assert (
        projets.filter(simulationprojet__status=SimulationProjet.STATUS_VALID).count()
        == 1
    )
    assert (
        projets.filter(simulationprojet__status=SimulationProjet.STATUS_DRAFT).count()
        == 4
    )
    assert (
        projets.filter(
            simulationprojet__status=SimulationProjet.STATUS_CANCELLED
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_view_with_one_status_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "status": SimulationProjet.STATUS_DRAFT,
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 4
    assert (
        projets.filter(simulationprojet__status=SimulationProjet.STATUS_DRAFT).count()
        == 4
    )


@pytest.mark.django_db
def test_view_with_filters(req, simulation, create_simulation_projets):
    filter_params = {
        "status": [SimulationProjet.STATUS_VALID, SimulationProjet.STATUS_DRAFT],
        "montant_previsionnel_min": 300_000,
        "montant_previsionnel_max": 400_000,
    }
    view = _get_view_with_filter(req, simulation, filter_params)
    projets = view.get_projet_queryset()

    assert projets.count() == 3

    assert (
        projets.filter(simulationprojet__status=SimulationProjet.STATUS_VALID).count()
        == 1
    )
    assert (
        projets.filter(simulationprojet__status=SimulationProjet.STATUS_DRAFT).count()
        == 2
    )
    for projet in projets:
        assert 300_000 <= projet.simulationprojet_set.first().montant <= 400_000


## Test with multiple simulations


def test_view_with_multiple_simulations(req, perimetre_departemental):
    demandeur = DemandeurFactory(departement=perimetre_departemental.departement)

    dossier_2024 = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        ds_date_depot=datetime(2023, 10, 1, tzinfo=UTC),
        ds_date_traitement=datetime(2024, 1, 1, tzinfo=UTC),
        annotations_montant_accorde=150_000,
        demande_montant=200_000,
        demande_dispositif_sollicite="DETR",
    )
    ProjetFactory(dossier_ds=dossier_2024, demandeur=demandeur)

    enveloppe = DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2024, montant=1_000_000
    )
    simulation_1 = SimulationFactory(enveloppe=enveloppe)
    simulation_2 = SimulationFactory(enveloppe=enveloppe)

    add_enveloppe_projets_to_simulation(simulation_1.id)
    add_enveloppe_projets_to_simulation(simulation_2.id)

    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "status": SimulationProjet.STATUS_DRAFT,
        },
    )
    projets = view.get_projet_queryset()
    assert projets.count() == 1

    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "montant_previsionnel_min": 180_000,
            "montant_previsionnel_max": 220_000,
        },
    )
    projets = view.get_projet_queryset()
    assert projets.count() == 1

    # When we modify one SimulationProjet, Filter works and is not influenced by the other Simulation
    ## Status
    simulation_1.simulationprojet_set.all().update(status=SimulationProjet.STATUS_VALID)
    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "status": SimulationProjet.STATUS_DRAFT,
        },
    )
    projets = view.get_projet_queryset()
    assert projets.count() == 0

    ## Montant
    simulation_1.simulationprojet_set.all().update(montant=100_000)
    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "montant_previsionnel_min": 180_000,
            "montant_previsionnel_max": 220_000,
        },
    )
    projets = view.get_projet_queryset()
    assert projets.count() == 0


@pytest.mark.django_db
def test_view_with_cout_total_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "cout_min": 2_000_000,
        "cout_max": 3_000_000,
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 5

    for status, count in [
        (SimulationProjet.STATUS_DRAFT, 2),
        (SimulationProjet.STATUS_VALID, 1),
        (SimulationProjet.STATUS_CANCELLED, 2),
    ]:
        assert projets.filter(simulationprojet__status=status).count() == count

    for projet in projets:
        assert 2_000_000 <= projet.assiette_or_cout_total <= 3_000_000


@pytest.mark.django_db
def test_view_with_montant_demande_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "montant_demande_min": 300_000,
        "montant_demande_max": 400_000,
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 5

    for status, count in [
        (SimulationProjet.STATUS_DRAFT, 2),
        (SimulationProjet.STATUS_VALID, 1),
        (SimulationProjet.STATUS_CANCELLED, 2),
    ]:
        assert projets.filter(simulationprojet__status=status).count() == count

    for projet in projets:
        assert 300_000 <= projet.dossier_ds.demande_montant <= 400_000


@pytest.mark.django_db
def test_view_with_porteur_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "porteur": "EPCI",
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 2

    for status, count in [
        (SimulationProjet.STATUS_DRAFT, 2),
        (SimulationProjet.STATUS_VALID, 0),
        (SimulationProjet.STATUS_CANCELLED, 0),
    ]:
        assert projets.filter(simulationprojet__status=status).count() == count

    for projet in projets:
        assert projet.dossier_ds.porteur_de_projet_nature.label == "EPCI"

    filter_params = {
        "porteur": "Communes",
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 5

    for status, count in [
        (SimulationProjet.STATUS_DRAFT, 2),
        (SimulationProjet.STATUS_VALID, 1),
        (SimulationProjet.STATUS_CANCELLED, 2),
    ]:
        assert projets.filter(simulationprojet__status=status).count() == count

    for projet in projets:
        assert projet.dossier_ds.porteur_de_projet_nature.label == "Commune"

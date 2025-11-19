from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.urls import resolve, reverse

from gsl_core.tests.factories import (
    ArrondissementFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
    RequestFactory,
)
from gsl_demarches_simplifiees.models import Dossier, NaturePorteurProjet
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    FieldMappingForComputerFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.models import Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import (
    DemandeurFactory,
    DotationProjetFactory,
    ProjetFactory,
)
from gsl_simulation.forms import _add_enveloppe_projets_to_simulation
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_simulation.views.simulation_views import (
    SimulationDetailView,
    SimulationListView,
)

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
def ds_field():
    return FieldMappingForComputerFactory(ds_field_id=101112)


@pytest.fixture
def simulations(perimetre_departemental):
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre_departemental)
    SimulationFactory(enveloppe=enveloppe)
    SimulationFactory(enveloppe=enveloppe)
    SimulationFactory()


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def projets(simulation, perimetre_departemental):
    other_perimeter = PerimetreDepartementalFactory()
    projets = []
    epci = NaturePorteurProjetFactory(label="EPCI", type=NaturePorteurProjet.EPCI)
    commune = NaturePorteurProjetFactory(
        label="Commune", type=NaturePorteurProjet.COMMUNES
    )
    for perimetre in (perimetre_departemental, other_perimeter):
        for year in (2024, 2025):
            DetrEnveloppeFactory(perimetre=perimetre, annee=year)
            DsilEnveloppeFactory(perimetre=perimetre, annee=year)

    for perimetre in (perimetre_departemental, other_perimeter):
        demandeur = DemandeurFactory()
        for dotation in ("DETR", "DSIL"):
            for state in (
                Dossier.STATE_ACCEPTE,
                Dossier.STATE_REFUSE,
                Dossier.STATE_SANS_SUITE,
            ):
                dossier_2024 = DossierFactory(
                    ds_state=state,
                    ds_date_depot=datetime(2023, 10, 1, tzinfo=UTC),
                    ds_date_traitement=datetime(2024, 1, 1, tzinfo=UTC),
                    demande_montant=200_000,
                    demande_dispositif_sollicite=dotation,
                    finance_cout_total=1_000_000,
                    annotations_montant_accorde_detr=150_000,
                    annotations_montant_accorde_dsil=150_000,
                    porteur_de_projet_nature=epci,
                    ds_demandeur__address__commune__departement=perimetre.departement,
                )
                projet_2024 = ProjetFactory(
                    dossier_ds=dossier_2024,
                    perimetre=perimetre,
                    demandeur=demandeur,
                )
                projets.append(projet_2024)

                dossier_2025 = DossierFactory(
                    ds_state=state,
                    ds_date_traitement=datetime(2025, 1, 1, tzinfo=UTC),
                    demande_montant=300_000,
                    annotations_montant_accorde_detr=120_000,
                    annotations_montant_accorde_dsil=120_000,
                    demande_dispositif_sollicite=dotation,
                    finance_cout_total=2_000_000,
                    porteur_de_projet_nature=commune,
                    ds_demandeur__address__commune__departement=perimetre.departement,
                )
                projet_2025 = ProjetFactory(
                    dossier_ds=dossier_2025,
                    demandeur=demandeur,
                    perimetre=perimetre,
                )
                projets.append(projet_2025)
            demandeur = DemandeurFactory()
            for state in (Dossier.STATE_EN_CONSTRUCTION, Dossier.STATE_EN_INSTRUCTION):
                dossier_2024 = DossierFactory(
                    ds_state=state,
                    ds_date_depot=datetime(2024, 2, 12, tzinfo=UTC),
                    ds_date_traitement=None,
                    demande_dispositif_sollicite=dotation,
                    demande_montant=400_000,
                    finance_cout_total=3_000_000,
                    porteur_de_projet_nature=commune,
                    ds_demandeur__address__commune__departement=perimetre.departement,
                )
                projet_2024 = ProjetFactory(
                    dossier_ds=dossier_2024,
                    demandeur=demandeur,
                    perimetre=perimetre,
                )
                projets.append(projet_2024)

                dossier_2025 = DossierFactory(
                    ds_state=state,
                    ds_date_depot=datetime(2025, 2, 12, tzinfo=UTC),
                    ds_date_traitement=None,
                    demande_dispositif_sollicite=dotation,
                    demande_montant=500_000,
                    finance_cout_total=4_000_000,
                    porteur_de_projet_nature=epci,
                    ds_demandeur__address__commune__departement=perimetre.departement,
                )
                projet_2025 = ProjetFactory(
                    dossier_ds=dossier_2025,
                    demandeur=demandeur,
                    perimetre=perimetre,
                )
                projets.append(projet_2025)
    for projet in projets:
        DotationProjetService.create_or_update_dotation_projet_from_projet(projet)
    return projets


def test_simulation_list_view(req, view, simulations):
    url = reverse("simulation:simulation-list")
    view.object_list = simulations
    view.request = req.get(url)

    assert view.get_queryset().count() == 2
    assert (
        view.get_queryset().first().created_at > view.get_queryset().last().created_at
    )


@pytest.fixture
def create_simulation_projets(simulation, projets):
    _add_enveloppe_projets_to_simulation(simulation)


# Test filters


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
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_ACCEPTED
        ).count()
        == 1
    )
    assert (
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_PROCESSING
        ).count()
        == 4
    )
    assert (
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_REFUSED
        ).count()
        == 1
    )
    assert (
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_DISMISSED
        ).count()
        == 1
    )


def test_view_with_one_status_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "status": SimulationProjet.STATUS_PROCESSING,
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 4
    assert (
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_PROCESSING
        ).count()
        == 4
    )


def test_view_with_filters(req, simulation, create_simulation_projets):
    filter_params = {
        "status": [
            SimulationProjet.STATUS_ACCEPTED,
            SimulationProjet.STATUS_PROCESSING,
        ],
        "montant_previsionnel_min": 120_000,
        "montant_previsionnel_max": 400_000,
    }
    view = _get_view_with_filter(req, simulation, filter_params)
    projets = view.get_projet_queryset()

    assert projets.count() == 3

    assert (
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_ACCEPTED
        ).count()
        == 1
    )
    assert (
        projets.filter(
            dotationprojet__simulationprojet__status=SimulationProjet.STATUS_PROCESSING
        ).count()
        == 2
    )
    for projet in projets:
        assert (
            120_000
            <= projet.dotationprojet_set.first().simulationprojet_set.first().montant
            <= 400_000
        )


def test_view_with_order(req, simulation, create_simulation_projets):
    filter_params = {
        "order": "-montant_previsionnel",
    }
    view = _get_view_with_filter(req, simulation, filter_params)
    projets = view.get_projet_queryset()

    assert projets.count() == 7
    assert (
        projets.first().dotationprojet_set.first().simulationprojet_set.first().montant
        == 500_000
    )


## Test with multiple simulations


def test_view_with_multiple_simulations(req, perimetre_departemental):
    state = Dossier.STATE_EN_INSTRUCTION
    dossier_2024 = DossierFactory(
        ds_state=state,
        ds_date_depot=datetime(2023, 10, 1, tzinfo=UTC),
        ds_date_traitement=datetime(2024, 1, 1, tzinfo=UTC),
        annotations_montant_accorde=150_000,
        demande_montant=200_000,
        demande_dispositif_sollicite="DETR",
    )
    projet = ProjetFactory(
        dossier_ds=dossier_2024,
        perimetre=perimetre_departemental,
    )

    enveloppe = DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2024, montant=1_000_000
    )
    simulation_1 = SimulationFactory(enveloppe=enveloppe)
    simulation_2 = SimulationFactory(enveloppe=enveloppe)

    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)
    _add_enveloppe_projets_to_simulation(simulation_1)
    _add_enveloppe_projets_to_simulation(simulation_2)

    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "status": SimulationProjet.STATUS_PROCESSING,
        },
    )
    projets = view.get_projet_queryset()
    assert projets.count() == 1

    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "montant_previsionnel_min": 130_000,
            "montant_previsionnel_max": 180_000,
        },
    )
    projets = view.get_projet_queryset()
    assert projets.count() == 1

    # When we modify one SimulationProjet, Filter works and is not influenced by the other Simulation
    ## Status
    simulation_1.simulationprojet_set.all().update(
        status=SimulationProjet.STATUS_ACCEPTED
    )
    view = _get_view_with_filter(
        req,
        simulation_1,
        {
            "status": SimulationProjet.STATUS_PROCESSING,
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


def test_view_with_cout_total_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "cout_min": 2_000_000,
        "cout_max": 3_000_000,
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 5

    for status, count in [
        (SimulationProjet.STATUS_PROCESSING, 2),
        (SimulationProjet.STATUS_ACCEPTED, 1),
        (SimulationProjet.STATUS_REFUSED, 1),
        (SimulationProjet.STATUS_DISMISSED, 1),
    ]:
        assert (
            projets.filter(dotationprojet__simulationprojet__status=status).count()
            == count
        )

    for projet in projets:
        for dotation_projet in projet.dotationprojet_set.all():
            assert 2_000_000 <= dotation_projet.assiette_or_cout_total <= 3_000_000


def test_view_with_montant_demande_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "montant_demande_min": 300_000,
        "montant_demande_max": 400_000,
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 5

    for status, count in [
        (SimulationProjet.STATUS_PROCESSING, 2),
        (SimulationProjet.STATUS_ACCEPTED, 1),
        (SimulationProjet.STATUS_REFUSED, 1),
        (SimulationProjet.STATUS_DISMISSED, 1),
    ]:
        assert (
            projets.filter(dotationprojet__simulationprojet__status=status).count()
            == count
        )

    for projet in projets:
        assert 300_000 <= projet.dossier_ds.demande_montant <= 400_000


def test_view_with_porteur_filter(req, simulation, create_simulation_projets):
    filter_params = {
        "porteur": "epci",
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 2

    for status, count in [
        (SimulationProjet.STATUS_PROCESSING, 2),
        (SimulationProjet.STATUS_ACCEPTED, 0),
        (SimulationProjet.STATUS_REFUSED, 0),
        (SimulationProjet.STATUS_DISMISSED, 0),
    ]:
        assert (
            projets.filter(dotationprojet__simulationprojet__status=status).count()
            == count
        )

    for projet in projets:
        assert projet.dossier_ds.porteur_de_projet_nature.type == "epci"

    filter_params = {
        "porteur": "communes",
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 5

    for status, count in [
        (SimulationProjet.STATUS_PROCESSING, 2),
        (SimulationProjet.STATUS_ACCEPTED, 1),
        (SimulationProjet.STATUS_REFUSED, 1),
        (SimulationProjet.STATUS_DISMISSED, 1),
    ]:
        assert (
            projets.filter(dotationprojet__simulationprojet__status=status).count()
            == count
        )

    for projet in projets:
        assert projet.dossier_ds.porteur_de_projet_nature.type == "communes"


def test_simulation_has_correct_territoire_choices():
    perimetre_arrondissement_A = PerimetreArrondissementFactory()
    perimetre_arrondissement_B = PerimetreArrondissementFactory()

    perimetre_departement_A = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement_A.departement,
    )
    _perimetre_departement_B = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement_B.departement,
    )
    perimetre_region_A = PerimetreRegionalFactory(
        region=perimetre_departement_A.region,
    )

    enveloppe = DsilEnveloppeFactory(perimetre=perimetre_departement_A)
    simulation = SimulationFactory(enveloppe=enveloppe)

    user = CollegueFactory(perimetre=perimetre_region_A)
    client = ClientWithLoggedUserFactory(user)
    url = reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})

    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context["territoire_choices"]) == 2
    assert response.context["territoire_choices"] == (
        perimetre_departement_A,
        perimetre_arrondissement_A,
    )


def test_view_with_territory_filter():
    perimetre_arrondissement_A = PerimetreArrondissementFactory()
    perimetre_arrondissement_B = PerimetreArrondissementFactory(
        arrondissement=ArrondissementFactory(
            departement=perimetre_arrondissement_A.departement
        )
    )

    perimetre_departement_A = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement_A.departement,
    )

    enveloppe = DetrEnveloppeFactory(perimetre=perimetre_departement_A)
    simulation = SimulationFactory(enveloppe=enveloppe)

    dotation_projets_A = DotationProjetFactory.create_batch(
        2, dotation=enveloppe.dotation, projet__perimetre=perimetre_arrondissement_A
    )
    for dotation_projet_A in dotation_projets_A:
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet=dotation_projet_A,
        )
    dotation_projets_B = DotationProjetFactory.create_batch(
        3, dotation=enveloppe.dotation, projet__perimetre=perimetre_arrondissement_B
    )

    for dotation_projet_B in dotation_projets_B:
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet=dotation_projet_B,
        )

    assert Projet.objects.count() == 5
    assert Projet.objects.for_perimetre(perimetre_departement_A).count() == 5
    assert Projet.objects.for_perimetre(perimetre_arrondissement_A).count() == 2
    assert Projet.objects.for_perimetre(perimetre_arrondissement_B).count() == 3

    user = CollegueFactory(perimetre=perimetre_departement_A)
    req = RequestFactory(user=user)
    filter_params = {
        "territoire": [perimetre_arrondissement_A.id],
    }
    view = _get_view_with_filter(req, simulation, filter_params)

    projets = view.get_projet_queryset()

    assert projets.count() == 2
    assert all(projet.perimetre == perimetre_arrondissement_A for projet in projets)


def test_get_projet_queryset_calls_prefetch(req, simulation, create_simulation_projets):
    filter_params = {}
    with patch("gsl_simulation.views.simulation_views.Prefetch") as mock_prefetch:
        view = _get_view_with_filter(req, simulation, filter_params)
        queryset = view.get_projet_queryset()

        assert queryset.exists()
        assert mock_prefetch.call_count == 2

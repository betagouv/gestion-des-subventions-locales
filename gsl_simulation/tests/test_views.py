import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
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
    NaturePorteurProjetFactory,
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
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import (
    DemandeurFactory,
    DotationProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tasks import add_enveloppe_projets_to_simulation
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
                    annotations_montant_accorde=150_000,
                    demande_montant=200_000,
                    demande_dispositif_sollicite=dotation,
                    finance_cout_total=1_000_000,
                    porteur_de_projet_nature=epci,
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
                    annotations_montant_accorde=120_000,
                    demande_dispositif_sollicite=dotation,
                    finance_cout_total=2_000_000,
                    porteur_de_projet_nature=commune,
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


def test_get_enveloppe_data(req, simulation, projets, perimetre_departemental):
    detr_enveloppe_2024 = DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2024, montant=1_000_000
    )
    simulation_2024 = SimulationFactory(enveloppe=detr_enveloppe_2024)
    view = SimulationDetailView()
    view.kwargs = {"slug": simulation_2024.slug}
    view.request = req.get(
        reverse("simulation:simulation-detail", kwargs={"slug": simulation_2024.slug})
    )
    view.object = simulation_2024

    enveloppe_data = view._get_enveloppe_data(simulation_2024)

    assert Projet.objects.count() == 40

    projet_filter_by_perimetre = Projet.objects.for_perimetre(perimetre_departemental)
    assert projet_filter_by_perimetre.count() == 20

    projet_filter_by_perimetre_and_dotation = projet_filter_by_perimetre.filter(
        dossier_ds__demande_dispositif_sollicite="DETR"
    )
    assert projet_filter_by_perimetre_and_dotation.count() == 10

    projet_qs_submitted_before_the_end_of_the_year = (
        projet_filter_by_perimetre_and_dotation.filter(
            dossier_ds__ds_date_depot__lt=datetime(
                simulation_2024.enveloppe.annee + 1, 1, 1, tzinfo=UTC
            ),
        )
    )
    assert projet_qs_submitted_before_the_end_of_the_year.count() == 5

    assert enveloppe_data["dotation"] == "DETR"
    assert enveloppe_data["montant"] == 1_000_000
    assert enveloppe_data["perimetre"] == perimetre_departemental
    assert enveloppe_data["validated_projets_count"] == 0
    assert enveloppe_data["refused_projets_count"] == 0
    assert enveloppe_data["projets_count"] == 5
    assert enveloppe_data["demandeurs"] == 2
    assert enveloppe_data["montant_asked"] == 200_000 * 3 + 400_000 * 2
    assert enveloppe_data["montant_accepte"] == 0


def test_get_validated_and_refused_projets_count_enveloppe_data(req, simulation):
    for montant in [100_000, 200_000, 300_000]:
        ProgrammationProjetFactory.create(
            enveloppe=simulation.enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            montant=montant,
        )

    ProgrammationProjetFactory.create_batch(
        2, enveloppe=simulation.enveloppe, status=ProgrammationProjet.STATUS_REFUSED
    )

    view = SimulationDetailView()
    view.request = req.get(
        reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
    )
    view.object = simulation
    enveloppe_data = view._get_enveloppe_data(simulation)

    assert enveloppe_data["validated_projets_count"] == 3
    assert enveloppe_data["montant_accepte"] == 600_000
    assert enveloppe_data["refused_projets_count"] == 2


@pytest.fixture
def create_simulation_projets(simulation, projets):
    add_enveloppe_projets_to_simulation(simulation.id)


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
    add_enveloppe_projets_to_simulation(simulation_1.id)
    add_enveloppe_projets_to_simulation(simulation_2.id)

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


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def simulation_projet(collegue, simulation) -> SimulationProjet:
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=1000,
        simulation=simulation,
    )


def test_patch_status_simulation_projet_with_accepted_value_with_htmx(
    client_with_user_logged, simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": f"{SimulationProjet.STATUS_ACCEPTED}"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(id=simulation_projet.id)
    dotation_projet = DotationProjet.objects.get(
        id=updated_simulation_projet.dotation_projet.id
    )

    assert response.status_code == 200
    assert updated_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED
    assert "1 projet validé" in response.content.decode()
    assert "0 projet refusé" in response.content.decode()
    assert "0 projet notifié" in response.content.decode()
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">1\xa0000\xa0€</span>'
        in response.content.decode()
    )


def test_patch_status_simulation_projet_with_refused_value_with_htmx(
    client_with_user_logged, simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": f"{SimulationProjet.STATUS_REFUSED}"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    simulation_projet.refresh_from_db()
    dotation_projet = DotationProjet.objects.get(
        id=simulation_projet.dotation_projet.id
    )

    assert response.status_code == 200
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
    assert dotation_projet.status == PROJET_STATUS_REFUSED
    assert "0 projet validé" in response.content.decode()
    assert "1 projet refusé" in response.content.decode()
    assert "0 projet notifié" in response.content.decode()
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">0\xa0€</span>'
        in response.content.decode()
    )


data_test = (
    (
        SimulationProjet.STATUS_ACCEPTED,
        "Le financement de ce projet vient d’être accepté avec la dotation DETR pour 1\xa0000,00\xa0€.",
        "valid",
    ),
    (
        SimulationProjet.STATUS_REFUSED,
        "Le financement de ce projet vient d’être refusé.",
        "cancelled",
    ),
    (
        SimulationProjet.STATUS_DISMISSED,
        "Le projet est classé sans suite.",
        "dismissed",
    ),
    (
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        "Le projet est accepté provisoirement dans cette simulation.",
        "provisionally_accepted",
    ),
    (
        SimulationProjet.STATUS_PROCESSING,
        "Le projet est revenu en traitement.",
        "draft",
    ),
)


@pytest.mark.parametrize("status, expected_message, expected_tag", data_test)
def test_patch_status_simulation_projet_with_refused_value_giving_message(
    client_with_user_logged, simulation_projet, status, expected_message, expected_tag
):
    if status == SimulationProjet.STATUS_PROCESSING:
        simulation_projet.status = SimulationProjet.STATUS_ACCEPTED
        simulation_projet.dotation_projet.status = PROJET_STATUS_ACCEPTED
        simulation_projet.dotation_projet.save()
        simulation_projet.save()

    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": status},
        follow=True,
    )

    assert response.status_code == 200

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1

    message = list(messages)[0]
    assert message.level == 20
    assert message.message == expected_message
    assert message.extra_tags == expected_tag


@pytest.mark.parametrize("data", ({"status": "invalid_status"}, {}))
def test_patch_status_simulation_projet_invalid_status(
    client_with_user_logged, simulation_projet, data
):
    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": "invalid"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(id=simulation_projet.id)
    assert response.status_code == 500
    assert updated_simulation_projet.status == SimulationProjet.STATUS_PROCESSING


@pytest.fixture
def accepted_simulation_projet(collegue, simulation) -> SimulationProjet:
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
    )

    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
        simulation=simulation,
    )


def test_patch_taux_simulation_projet(
    client_with_user_logged, accepted_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux", args=[accepted_simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"taux": "75.0"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(
        id=accepted_simulation_projet.id
    )

    assert response.status_code == 200
    assert updated_simulation_projet.taux == 75.0
    assert updated_simulation_projet.montant == 7_500
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">7\xa0500\xa0€</span>'
        in response.content.decode()
    )


@pytest.mark.parametrize("taux", ("-3", "100.1"))
def test_patch_taux_simulation_projet_with_wrong_value(
    client_with_user_logged, accepted_simulation_projet, taux, caplog
):
    url = reverse(
        "simulation:patch-simulation-projet-taux", args=[accepted_simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"taux": f"{taux}"},
        follow=True,
    )

    with caplog.at_level(logging.ERROR):
        accepted_simulation_projet.refresh_from_db()

    assert response.status_code == 500
    assert response.content == b'{"error": "An internal error has occurred."}'
    assert "must be between 0 and 100" in caplog.text
    assert accepted_simulation_projet.taux == 10
    assert accepted_simulation_projet.montant == 1_000


def test_patch_montant_simulation_projet(
    client_with_user_logged, accepted_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        {"montant": "1267,32"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(
        id=accepted_simulation_projet.id
    )

    assert response.status_code == 200
    assert updated_simulation_projet.montant == Decimal("1267.32")
    assert updated_simulation_projet.taux == Decimal("12.673")
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">1\xa0267\xa0€</span>'
        in response.content.decode()
    )


@pytest.mark.parametrize(
    "value, expected_value", (("True", True), ("False", False), ("", None))
)
def test_patch_detr_avis_commission_simulation_projet(
    client_with_user_logged, accepted_simulation_projet, value, expected_value
):
    url = reverse(
        "simulation:patch-dotation-projet",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        {"detr_avis_commission": value},
        follow=True,
    )

    updated_simulation_projet = SimulationProjet.objects.get(
        id=accepted_simulation_projet.id
    )

    assert response.status_code == 200
    assert (
        updated_simulation_projet.dotation_projet.detr_avis_commission is expected_value
    )


@pytest.mark.parametrize(
    "field, data, expected_value",
    (
        ("is_budget_vert", {"is_budget_vert": "True"}, True),
        ("is_budget_vert", {"is_budget_vert": "False"}, False),
        ("is_budget_vert", {"is_budget_vert": ""}, None),
        ("is_attached_to_a_crte", {"is_attached_to_a_crte": "on"}, True),
        ("is_attached_to_a_crte", {}, False),
        ("is_in_qpv", {"is_in_qpv": "on"}, True),
        ("is_in_qpv", {}, False),
    ),
)
def test_patch_projet(
    client_with_user_logged, accepted_simulation_projet, field, data, expected_value
):
    accepted_simulation_projet.projet.__setattr__(field, not (expected_value))
    accepted_simulation_projet.projet.save()

    data["dotations"] = [DOTATION_DSIL]

    url = reverse(
        "simulation:patch-projet",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        data,
        follow=True,
    )

    accepted_simulation_projet.projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.projet.__getattribute__(field) is expected_value


def test_get_projet_queryset_calls_prefetch(req, simulation, create_simulation_projets):
    filter_params = {}
    with patch("gsl_simulation.views.simulation_views.Prefetch") as mock_prefetch:
        view = _get_view_with_filter(req, simulation, filter_params)
        queryset = view.get_projet_queryset()

        assert queryset.exists()
        assert mock_prefetch.call_count == 2

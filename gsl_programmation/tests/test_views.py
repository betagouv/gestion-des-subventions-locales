from datetime import UTC, datetime

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
    RequestFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProjetFactory,
    SimulationFactory,
)
from gsl_programmation.views import SimulationDetailView, SimulationListView
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DemandeurFactory


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
    projets = []
    for perimetre in [perimetre_departemental, PerimetreDepartementalFactory()]:
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
                )
                projet_2025 = ProjetFactory(
                    dossier_ds=dossier_2025, demandeur=demandeur
                )
                projets.append(projet_2025)
    return projets


@pytest.mark.django_db
def test_simulation_view_status_code(req, view, simulations):
    url = reverse("programmation:simulation_list")
    view.object_list = simulations
    view.request = req.get(url)

    assert view.get_queryset().count() == 2


@pytest.mark.django_db
def test_get_enveloppe_data(req, simulation, projets, perimetre_departemental):
    view = SimulationDetailView()
    view.request = req.get(
        reverse("programmation:simulation_detail", kwargs={"slug": simulation.slug})
    )
    view.object = simulation
    enveloppe_data = view.get_enveloppe_data(simulation)

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

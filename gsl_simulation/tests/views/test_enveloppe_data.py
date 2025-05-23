from datetime import UTC, datetime

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gsl_core.tests.factories import PerimetreDepartementalFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.models import Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import DotationProjetFactory, SubmittedProjetFactory
from gsl_simulation.tests.factories import SimulationFactory
from gsl_simulation.views.simulation_views import SimulationDetailView


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        annee=2021, montant=1_000_000, perimetre=perimetre_departemental
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def submitted_projets(perimetre_departemental):
    projets = SubmittedProjetFactory.create_batch(
        4,
        perimetre=perimetre_departemental,
        dossier_ds__demande_montant=20_000,
        dossier_ds__ds_date_depot=datetime(2021, 12, 1, tzinfo=UTC),
        dossier_ds__demande_dispositif_sollicite="DETR",
    )
    for projet in projets:
        DotationProjetService.create_or_update_dotation_projet_from_projet(projet)
    return projets


@pytest.fixture
def programmation_projets(perimetre_departemental, detr_enveloppe):
    for _ in range(3):
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DETR,
            projet__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=30_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 10, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )
        ProgrammationProjetFactory(
            enveloppe=detr_enveloppe,
            status=ProgrammationProjet.STATUS_REFUSED,
            dotation_projet=dotation_projet,
        )

    for montant in (200_000, 300_000):
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DETR,
            projet__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=40_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 7, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )
        ProgrammationProjetFactory(
            enveloppe=detr_enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            montant=montant,
            dotation_projet=dotation_projet,
        )


@pytest.mark.django_db
def test_get_enveloppe_data(
    detr_enveloppe, simulation, programmation_projets, submitted_projets
):
    req = RequestFactory()
    view = SimulationDetailView()
    view.kwargs = {"slug": simulation.slug}
    view.request = req.get(
        reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
    )
    view.object = simulation
    enveloppe_data = view._get_enveloppe_data(simulation)

    assert Projet.objects.count() == 4 + 3 + 2  # = 9

    projet_filter_by_perimetre = Projet.objects.for_perimetre(detr_enveloppe.perimetre)
    assert projet_filter_by_perimetre.count() == 4 + 3 + 2  # = 9

    projet_filter_by_perimetre_and_dotation = projet_filter_by_perimetre.filter(
        dossier_ds__demande_dispositif_sollicite="DETR"
    )
    assert projet_filter_by_perimetre_and_dotation.count() == 4 + 3 + 2  # = 9

    projet_qs_submitted_before_the_end_of_the_year = (
        projet_filter_by_perimetre_and_dotation.filter(
            dossier_ds__ds_date_depot__lt=datetime(
                simulation.enveloppe.annee + 1, 1, 1, tzinfo=UTC
            ),
        )
    )
    assert projet_qs_submitted_before_the_end_of_the_year.count() == 4 + 3 + 2  # = 9

    assert enveloppe_data["dotation"] == "DETR"
    assert enveloppe_data["montant"] == 1_000_000
    assert enveloppe_data["perimetre"] == detr_enveloppe.perimetre
    assert enveloppe_data["validated_projets_count"] == 2
    assert enveloppe_data["refused_projets_count"] == 3
    assert enveloppe_data["projets_count"] == 9
    assert enveloppe_data["demandeurs"] == 9
    assert enveloppe_data["montant_asked"] == 20_000 * 4 + 30_000 * 3 + 40_000 * 2
    assert enveloppe_data["montant_accepte"] == 200_000 + 300_000

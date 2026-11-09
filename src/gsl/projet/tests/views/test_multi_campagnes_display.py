"""
Display of a multi-campagnes projet: each page only shows the enveloppe projets of
the campagne it is about.

Projet used throughout (N = default campagne):
- campagne N: DETR refused, DSIL dismissed
- campagne N+1: DETR processing, DSIL accepted
"""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from dn.sync.models import Dotation
from gsl.core.campagne import default_campagne
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.projet.constants import ProjetStatus
from gsl.projet.tests.factories import EnveloppeProjetFactory, ProjetFactory
from gsl.simulation.models import SimulationProjet
from gsl.simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db

CAMPAGNE_N = default_campagne()
CAMPAGNE_N_PLUS_1 = CAMPAGNE_N + 1

REFUSE = "❌ Refusé"
CLASSE_SANS_SUITE = "⛔️ Classé sans suite"
EN_TRAITEMENT = "🔄 En traitement"
ACCEPTE = "✅ Accepté"

STATUSES = {
    (Dotation.DETR, CAMPAGNE_N): ProjetStatus.REFUSED,
    (Dotation.DSIL, CAMPAGNE_N): ProjetStatus.DISMISSED,
    (Dotation.DETR, CAMPAGNE_N_PLUS_1): ProjetStatus.PROCESSING,
    (Dotation.DSIL, CAMPAGNE_N_PLUS_1): ProjetStatus.ACCEPTED,
}


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def client(perimetre):
    return ClientWithLoggedUserFactory(CollegueFactory(perimetre=perimetre))


@pytest.fixture
def projet(perimetre):
    return ProjetFactory(
        dossier_ds__perimetre=perimetre,
        dossier_ds__projet_intitule="Projet multi-campagnes",
    )


@pytest.fixture
def simulations(perimetre, projet):
    """One simulation per (dotation, campagne), holding the projet with the status
    of its enveloppe projet."""
    simulations = {}
    for (dotation, campagne), status in STATUSES.items():
        enveloppe_factory = (
            DetrEnveloppeFactory if dotation == Dotation.DETR else DsilEnveloppeFactory
        )
        enveloppe = enveloppe_factory(perimetre=perimetre, annee=campagne)
        enveloppe_projet = EnveloppeProjetFactory(
            projet=projet, enveloppe=enveloppe, status=status
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        SimulationProjetFactory(
            enveloppe_projet=enveloppe_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_FROM_PROJET_STATUS[status],
        )
        simulations[(dotation, campagne)] = simulation
    return simulations


# Liste des projets ====================================================================


@pytest.mark.parametrize(
    "campagne, expected_statuses",
    (
        (CAMPAGNE_N, (REFUSE, CLASSE_SANS_SUITE)),
        (CAMPAGNE_N_PLUS_1, (EN_TRAITEMENT, ACCEPTE)),
    ),
)
def test_projet_list_displays_both_dotations_of_the_campagne(
    client, simulations, campagne, expected_statuses
):
    response = client.get(reverse("projet:list", kwargs={"campagne": campagne}))

    assert response.status_code == 200
    (row,) = _table_rows(response, "table-projets")
    for status in expected_statuses:
        assert status in row
    for status in {REFUSE, CLASSE_SANS_SUITE, EN_TRAITEMENT, ACCEPTE} - set(
        expected_statuses
    ):
        assert status not in row


# Simulations ==========================================================================


@pytest.mark.parametrize(
    "dotation, campagne, main_status, other_dotation, other_status",
    (
        (Dotation.DETR, CAMPAGNE_N, REFUSE, Dotation.DSIL, CLASSE_SANS_SUITE),
        (Dotation.DSIL, CAMPAGNE_N, CLASSE_SANS_SUITE, Dotation.DETR, REFUSE),
        (Dotation.DETR, CAMPAGNE_N_PLUS_1, EN_TRAITEMENT, Dotation.DSIL, ACCEPTE),
        (Dotation.DSIL, CAMPAGNE_N_PLUS_1, ACCEPTE, Dotation.DETR, EN_TRAITEMENT),
    ),
)
def test_simulation_displays_the_other_dotation_of_the_campagne(
    client,
    simulations,
    dotation,
    campagne,
    main_status,
    other_dotation,
    other_status,
):
    simulation = simulations[(dotation, campagne)]

    response = client.get(
        reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
    )

    assert response.status_code == 200
    main_row, other_dotation_row = _table_rows(response, "table-simulation")
    assert main_status in main_row
    assert f"Informations pour la dotation {other_dotation}" in other_dotation_row
    assert other_status in other_dotation_row


# Programmations =======================================================================


@pytest.mark.parametrize(
    "dotation, campagne, main_status, other_dotation, other_status",
    (
        (Dotation.DETR, CAMPAGNE_N, REFUSE, Dotation.DSIL, CLASSE_SANS_SUITE),
        (Dotation.DSIL, CAMPAGNE_N, CLASSE_SANS_SUITE, Dotation.DETR, REFUSE),
        (Dotation.DSIL, CAMPAGNE_N_PLUS_1, ACCEPTE, Dotation.DETR, EN_TRAITEMENT),
    ),
)
def test_programmation_displays_the_other_dotation_of_the_campagne(
    client,
    simulations,
    dotation,
    campagne,
    main_status,
    other_dotation,
    other_status,
):
    response = client.get(_programmation_url(dotation, campagne))

    assert response.status_code == 200
    main_row, other_dotation_row = _table_rows(response, "table-programmation")
    assert main_status in main_row
    assert f"Informations pour la dotation {other_dotation}" in other_dotation_row
    assert other_status in other_dotation_row


def test_programmation_does_not_display_the_projet_not_programmed_on_the_campagne(
    client, simulations
):
    response = client.get(_programmation_url(Dotation.DETR, CAMPAGNE_N_PLUS_1))

    assert response.status_code == 200
    assert _table_rows(response, "table-programmation") == ["Liste vide."]
    assert "Projet multi-campagnes" not in response.content.decode()


def _programmation_url(dotation, campagne):
    return reverse(
        "programmation:programmation-projet-list-dotation",
        kwargs={"dotation": dotation, "campagne": campagne},
    )


def _table_rows(response, table_id: str) -> list[str]:
    """Text of each row of the body of the table `table_id`."""
    soup = BeautifulSoup(response.content, "html.parser")
    return [
        row.get_text(" ", strip=True)
        for row in soup.select(f"table#{table_id} tbody tr")
        if row.find("td")
    ]

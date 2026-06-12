"""End-to-end tests for the redesigned filter bar (fixed row, extra disclosure,
dismissible active-filter tags). Drives the three list views that share the
`includes/_projet_list_filters.html` template through the test client."""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_demarches_simplifiees.tests.factories import NaturePorteurProjetFactory
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def user(perimetre):
    return CollegueFactory(perimetre=perimetre)


@pytest.fixture
def client(user):
    return ClientWithLoggedUserFactory(user)


def _soup(response):
    return BeautifulSoup(response.content.decode(), "html.parser")


def _active_tags(soup):
    return soup.select("ul.filters-active-tags a.fr-tag")


def _tag_with(soup, text):
    for tag in _active_tags(soup):
        if text in tag.get_text(strip=True):
            return tag
    return None


# --- Projets list ---


def test_no_filter_hides_extra_panel_and_renders_no_tags(client, perimetre):
    ProjetFactory(dossier_ds__perimetre=perimetre)
    response = client.get(reverse("projet:list"))
    assert response.status_code == 200
    soup = _soup(response)

    # Fixed fields always present
    assert soup.select_one('input[name="search"]') is not None
    assert soup.select_one("#filter-montant_demande") is not None

    # Extra panel collapsed (DSFR fr-collapse), no active tags
    extra = soup.select_one("#filters-extra")
    assert "fr-collapse" in extra["class"]
    assert _active_tags(soup) == []

    toggle = soup.select_one("#filters-toggle")
    assert toggle["aria-expanded"] == "false"


def test_active_filters_render_dismissible_tags(client, perimetre):
    ProjetFactory(dossier_ds__perimetre=perimetre)
    response = client.get(
        reverse("projet:list"),
        data={
            "search": "foo",
            "montant_demande_min": "1000",
            "montant_demande_max": "5000",
            "order": "cout",
        },
    )
    assert response.status_code == 200
    soup = _soup(response)

    search_tag = _tag_with(soup, "Recherche « foo »")
    montant_tag = _tag_with(soup, "Montant demandé")
    order_tag = _tag_with(soup, "Trié par")
    assert search_tag is not None
    assert montant_tag is not None
    assert order_tag is not None

    # Each tag drops only its own GET key(s), keeping the others.
    search_href = search_tag["href"]
    assert "search=foo" not in search_href
    assert "montant_demande_min=1000" in search_href
    assert "order=cout" in search_href

    montant_href = montant_tag["href"]
    assert "montant_demande_min" not in montant_href
    assert "montant_demande_max" not in montant_href
    assert "search=foo" in montant_href
    assert "order=cout" in montant_href

    order_href = order_tag["href"]
    assert "order=" not in order_href
    assert "search=foo" in order_href
    assert "montant_demande_min=1000" in order_href


def test_active_extra_filter_stays_collapsed_but_shows_tag(client, perimetre):
    """An active extra filter is surfaced as a tag, but the panel stays closed."""
    NaturePorteurProjetFactory(label="EPCI", type=NaturePorteurProjet.EPCI)
    ProjetFactory(dossier_ds__perimetre=perimetre)
    response = client.get(reverse("projet:list"), data={"porteur": "epci"})
    assert response.status_code == 200
    soup = _soup(response)

    # Panel is always collapsed on load; the active filter shows below as a tag.
    extra = soup.select_one("#filters-extra")
    assert "fr-collapse" in extra["class"]
    assert soup.select_one("#filters-toggle")["aria-expanded"] == "false"
    assert _tag_with(soup, "Demandeur") is not None


# --- Programmation list (shared template, different filterset) ---


def test_programmation_list_renders_fixed_fields_and_tags(client, perimetre):
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre, annee=2024)
    ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        enveloppe=enveloppe,
    )
    url = reverse(
        "gsl_programmation:programmation-projet-list-dotation",
        kwargs={"dotation": "DETR"},
    )
    response = client.get(url, data={"search": "bar"})
    assert response.status_code == 200
    soup = _soup(response)

    # montant_retenu is a fixed field present on the programmation filterset
    assert soup.select_one('input[name="search"]') is not None
    assert soup.select_one("#filter-montant_retenu") is not None
    assert _tag_with(soup, "Recherche « bar »") is not None


# --- Simulation detail (shared template, montant_previsionnel replaces montant_retenu) ---


def test_simulation_detail_fixed_row_shows_montant_previsionnel(client, perimetre):
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    SimulationProjetFactory(
        simulation=simulation,
        dotation_projet__dotation=enveloppe.dotation,
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
    )
    url = reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
    response = client.get(url, data={"search": "baz"})
    assert response.status_code == 200
    soup = _soup(response)

    # The fixed row surfaces montant_previsionnel in place of the absent montant_retenu
    assert soup.select_one('input[name="search"]') is not None
    assert soup.select_one("#filter-montant_retenu") is None
    assert soup.select_one("#filter-montant_previsionnel") is not None
    assert _tag_with(soup, "Recherche « baz »") is not None

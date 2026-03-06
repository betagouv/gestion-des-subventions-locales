import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_simulation.tests.factories import SimulationFactory


@pytest.fixture
def departement():
    return DepartementFactory()


@pytest.fixture
def perimetre(departement):
    return PerimetreDepartementalFactory(departement=departement)


@pytest.fixture
def simulation(perimetre):
    return SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre),
    )


@pytest.fixture
def client_in_perimetre(perimetre):
    collegue = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def client_outside_perimetre():
    collegue = CollegueFactory()
    return ClientWithLoggedUserFactory(collegue)


def _url(simulation):
    return reverse(
        "gsl_simulation:simulation-columns-visibility",
        kwargs={"slug": simulation.slug},
    )


@pytest.mark.django_db
def test_post_valid_columns_visibility(client_in_perimetre, simulation):
    response = client_in_perimetre.post(
        _url(simulation),
        {"date-depot": "false", "demandeur": "true"},
    )
    assert response.status_code == 204
    simulation.refresh_from_db()
    assert simulation.columns_visibility == {"date-depot": False, "demandeur": True}


@pytest.mark.django_db
def test_post_invalid_key_returns_400(client_in_perimetre, simulation):
    response = client_in_perimetre.post(
        _url(simulation),
        {"unknown-column": "true"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_unauthorized_user_gets_404(client_outside_perimetre, simulation):
    response = client_outside_perimetre.post(
        _url(simulation),
        {"date-depot": "false"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_columns_visibility_persists_across_updates(client_in_perimetre, simulation):
    client_in_perimetre.post(
        _url(simulation),
        {"date-depot": "false", "demandeur": "true"},
    )

    client_in_perimetre.post(
        _url(simulation),
        {"date-depot": "true", "demandeur": "false"},
    )

    simulation.refresh_from_db()
    assert simulation.columns_visibility == {"date-depot": True, "demandeur": False}

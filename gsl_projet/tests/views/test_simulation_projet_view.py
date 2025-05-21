# TODO move all tests from ../test_views.py in this file or directory


import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def client_with_user_logged(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def simulation_projet(perimetre):
    dotation_projet = DotationProjetFactory(
        projet__perimetre=perimetre,
        dotation=DOTATION_DETR,
    )
    simulation = SimulationFactory(enveloppe=DetrEnveloppeFactory(perimetre=perimetre))
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
    )


@pytest.mark.django_db
def test_projet_note_form_save(client_with_user_logged, simulation_projet):
    projet = simulation_projet.projet
    assert projet.notes.count() == 0

    url = reverse(
        "simulation:simulation-projet-tab",
        kwargs={"pk": simulation_projet.pk, "tab": "annotations"},
    )
    response = client_with_user_logged.post(
        url,
        data={
            "title": "titre",
            "content": "contenu",
        },
        follow=True,
    )
    assert response.status_code == 200
    projet.refresh_from_db()
    assert projet.notes.count() == 1
    assert projet.notes.first().title == "titre"
    assert projet.notes.first().content == "contenu"

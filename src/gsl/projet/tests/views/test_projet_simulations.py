import pytest
from django.urls import reverse

from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl.programmation.tests.factories import DetrEnveloppeFactory
from gsl.simulation.tests.factories import SimulationFactory, SimulationProjetFactory

from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def test_simulations_are_grouped_by_campagne_most_recent_first():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    for annee in (2026, 2027):
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre, annee=annee)
        SimulationProjetFactory(
            enveloppe_projet=EnveloppeProjetFactory(projet=projet, enveloppe=enveloppe),
            simulation=SimulationFactory(
                enveloppe=enveloppe, title=f"Simulation de {annee}"
            ),
        )
    client = ClientWithLoggedUserFactory(CollegueFactory(perimetre=perimetre))

    response = client.get(
        reverse("projet:get-projet-simulations", kwargs={"projet_id": projet.id})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert (
        content.index('id="simulations-campagne-2027"')
        < content.index("Simulation de 2027")
        < content.index('id="simulations-campagne-2026"')
        < content.index("Simulation de 2026")
    )


def test_no_simulation():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    client = ClientWithLoggedUserFactory(CollegueFactory(perimetre=perimetre))

    response = client.get(
        reverse("projet:get-projet-simulations", kwargs={"projet_id": projet.id})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Aucune simulation pour ce projet" in content
    assert 'id="simulations-campagne-' not in content

import pytest
from django.urls import reverse

from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.simulation.tests.factories import SimulationFactory, SimulationProjetFactory

from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def test_simulations_are_grouped_by_enveloppe_projet_most_recent_campagne_first_then_by_dotation():
    perimetre = PerimetreDepartementalFactory()
    perimetre_regional = PerimetreRegionalFactory(region=perimetre.region)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    enveloppe_projets = {}
    for annee in (2026, 2027):
        for enveloppe in (
            DsilEnveloppeFactory(perimetre=perimetre_regional, annee=annee),
            DetrEnveloppeFactory(perimetre=perimetre, annee=annee),
        ):
            enveloppe_projet = EnveloppeProjetFactory(
                projet=projet, enveloppe=enveloppe
            )
            enveloppe_projets[(enveloppe.dotation, annee)] = enveloppe_projet
            SimulationProjetFactory(
                enveloppe_projet=enveloppe_projet,
                simulation=SimulationFactory(
                    enveloppe=enveloppe,
                    title=f"Simulation {enveloppe.dotation} de {annee}",
                ),
            )
    client = ClientWithLoggedUserFactory(CollegueFactory(perimetre=perimetre))

    response = client.get(
        reverse("projet:get-projet-simulations", kwargs={"projet_id": projet.id})
    )

    assert response.status_code == 200
    content = response.content.decode()
    positions = []
    for dotation, annee in (
        ("DETR", 2027),
        ("DSIL", 2027),
        ("DETR", 2026),
        ("DSIL", 2026),
    ):
        enveloppe_projet = enveloppe_projets[(dotation, annee)]
        positions.append(
            content.index(f'id="simulations-enveloppe-projet-{enveloppe_projet.pk}"')
        )
        positions.append(content.index(f"{dotation} - Campagne {annee}"))
        positions.append(content.index(f"Simulation {dotation} de {annee}"))
    assert positions == sorted(positions)


def test_simulations_of_the_same_enveloppe_projet_are_in_the_same_bloc():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre, annee=2027)
    enveloppe_projet = EnveloppeProjetFactory(projet=projet, enveloppe=enveloppe)
    for title in ("Première simulation", "Seconde simulation"):
        SimulationProjetFactory(
            enveloppe_projet=enveloppe_projet,
            simulation=SimulationFactory(enveloppe=enveloppe, title=title),
        )
    client = ClientWithLoggedUserFactory(CollegueFactory(perimetre=perimetre))

    response = client.get(
        reverse("projet:get-projet-simulations", kwargs={"projet_id": projet.id})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert content.count('id="simulations-enveloppe-projet-') == 1
    assert "Première simulation" in content
    assert "Seconde simulation" in content


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
    assert 'id="simulations-enveloppe-projet-' not in content

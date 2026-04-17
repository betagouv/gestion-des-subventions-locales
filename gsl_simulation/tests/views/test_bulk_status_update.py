from typing import cast

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, PROJET_STATUS_PROCESSING
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


def _make_simu_projet(collegue, simulation, **kwargs):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return cast(
        SimulationProjet,
        SimulationProjetFactory(
            dotation_projet=dotation_projet,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=1000,
            simulation=simulation,
            **kwargs,
        ),
    )


def _bulk_url(status):
    return reverse(
        "simulation:simulation-projet-bulk-update-simulation-status", args=[status]
    )


def test_bulk_status_update_marks_all_selected_rows(
    client_with_user_logged, collegue, simulation
):
    sp1 = _make_simu_projet(collegue, simulation)
    sp2 = _make_simu_projet(collegue, simulation)
    sp3 = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED),
        data={"simulation_projet_ids": f"{sp1.id},{sp2.id},{sp3.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Refresh") == "true"
    for sp in (sp1, sp2, sp3):
        sp.refresh_from_db()
        assert sp.status == SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED

    assert list(get_messages(response.wsgi_request)) == []


def test_bulk_status_update_rejects_ids_outside_user_perimeter(
    client_with_user_logged, collegue, simulation
):
    mine = _make_simu_projet(collegue, simulation)

    other_perimetre = PerimetreDepartementalFactory()
    other_enveloppe = DetrEnveloppeFactory(perimetre=other_perimetre, annee=2025)
    other_simulation = SimulationFactory(enveloppe=other_enveloppe)
    other_dotation = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=other_perimetre,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    outside = SimulationProjetFactory(
        dotation_projet=other_dotation,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=1000,
        simulation=other_simulation,
    )

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED),
        data={"simulation_projet_ids": f"{mine.id},{outside.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404
    mine.refresh_from_db()
    assert mine.status == SimulationProjet.STATUS_PROCESSING


def test_bulk_status_update_rejects_programmed_status(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING


def test_bulk_status_update_skips_notified_projects(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)
    sp_notified = _make_simu_projet(collegue, simulation)
    sp_notified.projet.notified_at = timezone.now()
    sp_notified.projet.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_REFUSED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_notified.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    sp_ok.refresh_from_db()
    sp_notified.refresh_from_db()
    assert sp_ok.status == SimulationProjet.STATUS_PROVISIONALLY_REFUSED
    assert sp_notified.status == SimulationProjet.STATUS_PROCESSING

    msgs = list(get_messages(response.wsgi_request))
    assert any("1 projet" in m.message and "ignoré" in m.message for m in msgs)


def test_bulk_status_update_skips_projet_with_final_source_status(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)
    sp_final = _make_simu_projet(collegue, simulation)
    sp_final.status = SimulationProjet.STATUS_ACCEPTED
    sp_final.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_final.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    sp_ok.refresh_from_db()
    sp_final.refresh_from_db()
    assert sp_ok.status == SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    assert sp_final.status == SimulationProjet.STATUS_ACCEPTED

    msgs = list(get_messages(response.wsgi_request))
    assert any("1 projet" in m.message and "ignoré" in m.message for m in msgs)


def test_bulk_status_update_empty_selection_shows_error(
    client_with_user_logged, simulation
):
    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROCESSING),
        data={"simulation_projet_ids": ""},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    msgs = list(get_messages(response.wsgi_request))
    assert len(msgs) == 1
    assert "Aucun projet" in msgs[0].message


def test_bulk_status_update_requires_htmx(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)
    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED),
        data={"simulation_projet_ids": f"{sp.id}"},
    )
    assert response.status_code == 400

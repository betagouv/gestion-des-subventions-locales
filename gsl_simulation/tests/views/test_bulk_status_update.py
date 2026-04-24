import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import (
    SimulationFactory,
    SimulationProjetFactory,
    make_detr_simu_projet,
)

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
    return make_detr_simu_projet(collegue.perimetre, simulation, **kwargs)


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


@pytest.mark.parametrize(
    "status",
    [SimulationProjet.STATUS_REFUSED, SimulationProjet.STATUS_DISMISSED],
)
def test_bulk_status_update_rejects_refused_and_dismissed(
    client_with_user_logged, collegue, simulation, status
):
    sp = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        _bulk_url(status),
        data={"simulation_projet_ids": f"{sp.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING


def test_bulk_status_update_to_accepted_returns_confirmation_modal(
    client_with_user_logged, collegue, simulation
):
    sp1 = _make_simu_projet(collegue, simulation)
    sp2 = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp1.id},{sp2.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Refresh") != "true"
    assert b"bulk-status-confirm-modal" in response.content
    assert b"Lancer le traitement" in response.content
    from gsl_simulation.models import BulkStatusJob

    assert BulkStatusJob.objects.count() == 0
    for sp in (sp1, sp2):
        sp.refresh_from_db()
        assert sp.status == SimulationProjet.STATUS_PROCESSING


def test_bulk_status_update_to_pending_returns_confirmation_modal_if_any_row_is_accepted(
    client_with_user_logged, collegue, simulation
):
    pending = _make_simu_projet(collegue, simulation)
    accepted = _make_simu_projet(
        collegue,
        simulation,
        dotation_status=PROJET_STATUS_ACCEPTED,
        simu_status=SimulationProjet.STATUS_ACCEPTED,
    )

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED),
        data={"simulation_projet_ids": f"{pending.id},{accepted.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Refresh") != "true"
    assert b"bulk-status-confirm-modal" in response.content


def test_bulk_status_update_rejects_notified_projets(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(
        collegue,
        simulation,
        dotation_status=PROJET_STATUS_ACCEPTED,
        simu_status=SimulationProjet.STATUS_ACCEPTED,
    )
    sp_notified = _make_simu_projet(
        collegue,
        simulation,
        dotation_status=PROJET_STATUS_ACCEPTED,
        simu_status=SimulationProjet.STATUS_ACCEPTED,
    )
    sp_notified.projet.notified_at = timezone.now()
    sp_notified.projet.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_notified.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404
    sp_ok.refresh_from_db()
    sp_notified.refresh_from_db()
    assert sp_ok.status == SimulationProjet.STATUS_ACCEPTED
    assert sp_notified.status == SimulationProjet.STATUS_ACCEPTED


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


# --------------------------------------------------------------------------
# Pre-flight validation (introduced with the upfront-errors modal)
# --------------------------------------------------------------------------


def test_preflight_to_accepted_with_missing_assiette_returns_preflight_modal(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)
    sp_blocked = _make_simu_projet(collegue, simulation)
    sp_blocked.dotation_projet.assiette = None
    sp_blocked.dotation_projet.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_blocked.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b"bulk-status-confirm-modal" in response.content
    assert (
        "L'assiette subventionnable n'est pas définie pour 1 projet.".encode()
        in response.content
    )
    sp_ok.refresh_from_db()
    sp_blocked.refresh_from_db()
    assert sp_ok.status == SimulationProjet.STATUS_PROCESSING
    assert sp_blocked.status == SimulationProjet.STATUS_PROCESSING
    assert b"simulation_projet_ids" in response.content
    assert f'value="{sp_ok.id}"'.encode() in response.content
    assert f'value="{sp_blocked.id}"'.encode() not in response.content


def test_preflight_to_accepted_with_all_rows_blocked_returns_error_modal(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)
    sp.dotation_projet.assiette = None
    sp.dotation_projet.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b"Aucun projet modifiable" in response.content
    assert b"Modifier</button>" not in response.content
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING


def test_preflight_to_accepted_without_ds_id_returns_error_modal(
    perimetre_departemental, simulation
):
    user = CollegueFactory(perimetre=perimetre_departemental)
    client = ClientWithLoggedUserFactory(user)
    sp = _make_simu_projet(user, simulation)

    response = client.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Droits utilisateurs manquants".encode() in response.content
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING


def test_preflight_without_ds_id_but_no_dn_target_commits_directly(
    perimetre_departemental, simulation
):
    user = CollegueFactory(perimetre=perimetre_departemental)
    client = ClientWithLoggedUserFactory(user)
    sp = _make_simu_projet(user, simulation)

    response = client.post(
        _bulk_url(SimulationProjet.STATUS_PROVISIONALLY_REFUSED),
        data={"simulation_projet_ids": f"{sp.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Refresh") == "true"
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROVISIONALLY_REFUSED


def test_preflight_montant_exceeds_assiette_blocks_row(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)
    sp_blocked = _make_simu_projet(collegue, simulation)
    sp_blocked.dotation_projet.assiette = 100
    sp_blocked.dotation_projet.save()
    sp_blocked.montant = 5000
    sp_blocked.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_blocked.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b"bulk-status-confirm-modal" in response.content
    assert (
        "Le montant accordé est supérieur à l'assiette subventionnable pour 1 projet.".encode()
        in response.content
    )


def test_preflight_groups_blockers_by_reason(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)
    sp_missing = _make_simu_projet(collegue, simulation)
    sp_missing.dotation_projet.assiette = None
    sp_missing.dotation_projet.save()
    sp_exceeds = _make_simu_projet(collegue, simulation)
    sp_exceeds.dotation_projet.assiette = 100
    sp_exceeds.dotation_projet.save()
    sp_exceeds.montant = 5000
    sp_exceeds.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_missing.id},{sp_exceeds.id}"},
        headers={"HX-Request": "true"},
    )

    assert (
        "L'assiette subventionnable n'est pas définie pour 1 projet.".encode()
        in response.content
    )
    assert (
        "Le montant accordé est supérieur à l'assiette subventionnable pour 1 projet.".encode()
        in response.content
    )


def test_preflight_with_no_blockers_falls_through_to_confirm_modal(
    client_with_user_logged, collegue, simulation
):
    sp1 = _make_simu_projet(collegue, simulation)
    sp2 = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp1.id},{sp2.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b"bulk-status-confirm-modal" in response.content
    assert b"Lancer le traitement" in response.content
    assert b"ne peut pas" not in response.content
    assert b"ne peuvent pas" not in response.content


def test_preflight_modal_for_dn_target_posts_to_job_start(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)
    sp_blocked = _make_simu_projet(collegue, simulation)
    sp_blocked.dotation_projet.assiette = None
    sp_blocked.dotation_projet.save()

    response = client_with_user_logged.post(
        _bulk_url(SimulationProjet.STATUS_ACCEPTED),
        data={"simulation_projet_ids": f"{sp_ok.id},{sp_blocked.id}"},
        headers={"HX-Request": "true"},
    )

    assert reverse("simulation:bulk-status-job-start").encode() in response.content


def test_preflight_survivors_posted_back_commits_via_async_job(
    client_with_user_logged, collegue, simulation
):
    sp_ok = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        reverse("simulation:bulk-status-job-start"),
        data={
            "simulation": simulation.pk,
            "target_status": SimulationProjet.STATUS_ACCEPTED,
            "simulation_projet_ids": f"{sp_ok.id}",
        },
        headers={"HX-Request": "true"},
    )

    # Smoke test that the async path accepts the survivors list produced by
    # the preflight modal. Full job coverage lives in test_bulk_status_job_views.
    assert response.status_code in (200, 204)

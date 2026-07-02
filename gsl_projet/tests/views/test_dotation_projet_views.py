import pytest
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
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def accepted_simulation_projet(collegue, perimetre_departemental):
    detr_enveloppe = DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )
    simulation = SimulationFactory(enveloppe=detr_enveloppe)
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__dossier_ds__perimetre=collegue.perimetre,
        projet__is_budget_vert=False,
        dotation=DOTATION_DETR,
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
        simulation=simulation,
    )


@pytest.fixture
def processing_dotation_projet(perimetre_departemental):
    return DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__dossier_ds__perimetre=perimetre_departemental,
        projet__notified_at=None,
    )


def _assiette_url(dp):
    return reverse("gsl_projet:patch-dotation-projet-assiette", kwargs={"pk": dp.pk})


def test_patch_assiette_saves_value(
    client_with_user_logged, processing_dotation_projet
):
    client_with_user_logged.post(
        _assiette_url(processing_dotation_projet), {"assiette": "50000"}
    )
    processing_dotation_projet.refresh_from_db()
    assert processing_dotation_projet.assiette == 50_000


def test_patch_assiette_shows_success_message(
    client_with_user_logged, processing_dotation_projet
):
    response = client_with_user_logged.post(
        _assiette_url(processing_dotation_projet), {"assiette": "50000"}, follow=True
    )
    messages = [m.message for m in response.context["messages"]]
    assert any("enregistrées avec succès" in m for m in messages)


def test_patch_assiette_invalid_does_not_save(
    client_with_user_logged, processing_dotation_projet
):
    client_with_user_logged.post(
        _assiette_url(processing_dotation_projet), {"assiette": ""}
    )
    processing_dotation_projet.refresh_from_db()
    assert processing_dotation_projet.assiette == 10_000


def test_patch_assiette_invalid_stores_errors_in_session(
    client_with_user_logged, processing_dotation_projet
):
    client_with_user_logged.post(
        _assiette_url(processing_dotation_projet), {"assiette": ""}
    )
    assert (
        f"assiette_errors_{processing_dotation_projet.pk}"
        in client_with_user_logged.session
    )


def test_patch_assiette_get_returns_405(
    client_with_user_logged, processing_dotation_projet
):
    response = client_with_user_logged.get(_assiette_url(processing_dotation_projet))
    assert response.status_code == 405


def test_patch_assiette_notified_projet_returns_404(
    client_with_user_logged, perimetre_departemental
):
    dp = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=perimetre_departemental,
        projet__notified_at=timezone.now(),
    )
    response = client_with_user_logged.post(_assiette_url(dp), {"assiette": "50000"})
    assert response.status_code == 404


def test_patch_assiette_out_of_perimeter_returns_404(client_with_user_logged):
    other_perimetre = PerimetreDepartementalFactory()
    dp = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=other_perimetre,
        projet__notified_at=None,
    )
    response = client_with_user_logged.post(_assiette_url(dp), {"assiette": "50000"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "value, expected_value", (("True", True), ("False", False), ("", None))
)
def test_patch_detr_avis_commission(
    client_with_user_logged, accepted_simulation_projet, value, expected_value
):
    url = reverse(
        "projet:patch-dotation-projet",
        kwargs={"pk": accepted_simulation_projet.dotation_projet.pk},
    )
    response = client_with_user_logged.post(
        url,
        {"detr_avis_commission": value},
        follow=True,
    )

    assert response.status_code == 200
    accepted_simulation_projet.dotation_projet.refresh_from_db()
    assert (
        accepted_simulation_projet.dotation_projet.detr_avis_commission
        is expected_value
    )

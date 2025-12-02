import pytest
from django.shortcuts import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db()


def test_projet_detail_page_has_no_status_and_notification_status_card_when_all_dotation_projet_have_processing_status():
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(perimetre=perimetre)
    DotationProjetFactory(projet=projet, status=PROJET_STATUS_PROCESSING)
    url = reverse(
        "gsl_projet:get-projet",
        kwargs={"projet_id": projet.id},
    )
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    assert response.context["projet"].all_dotations_have_processing_status is True
    assert "Décision de financement du projet" not in response.content.decode()


@pytest.mark.parametrize(
    "status", (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED)
)
def test_projet_detail_page_has_status_and_notification_status_card_with_not_processing_simple_dotation(
    status,
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(perimetre=perimetre)
    DotationProjetFactory(projet=projet, status=status)
    url = reverse(
        "gsl_projet:get-projet",
        kwargs={"projet_id": projet.id},
    )
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    assert response.context["projet"].all_dotations_have_processing_status is False
    assert "Décision de financement du projet" in response.content.decode()
    # assert "Notifier le demandeur" in response.content.decode()
    # TODO DUN: precise this ⬆️


@pytest.mark.parametrize(
    "dotation_status_1, dotation_status_2",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING),
    ),
)
def test_projet_detail_page_has_status_and_notification_status_card_with_not_processing_double_dotations(
    dotation_status_1, dotation_status_2
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(perimetre=perimetre)
    DotationProjetFactory(projet=projet, status=dotation_status_1)
    DotationProjetFactory(projet=projet, status=dotation_status_2)
    url = reverse(
        "gsl_projet:get-projet",
        kwargs={"projet_id": projet.id},
    )
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    assert response.context["projet"].all_dotations_have_processing_status is False
    assert "Décision de financement du projet" in response.content.decode()

from datetime import datetime

import pytest
from django.shortcuts import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
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
    assert "Notifier le demandeur" not in response.content.decode(), (
        "Notify button is never displayed in projet page from main tab #1"
    )


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
    assert "Notifier le demandeur" not in response.content.decode(), (
        "Notify button is never displayed in projet page from main tab #1"
    )


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
    assert "Notifier le demandeur" not in response.content.decode(), (
        "Notify button is never displayed in projet page from main tab #1"
    )


@pytest.mark.parametrize(
    "dotation_status_1, dotation_status_2, notification_status_message",
    (
        (
            PROJET_STATUS_ACCEPTED,
            PROJET_STATUS_ACCEPTED,
            "À notifier",
        ),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, "À notifier"),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, "À notifier"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, "À notifier"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, "À notifier"),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, "À notifier"),
        (
            PROJET_STATUS_ACCEPTED,
            PROJET_STATUS_PROCESSING,
            "En attente de la décision DSIL",
        ),
        (
            PROJET_STATUS_REFUSED,
            PROJET_STATUS_PROCESSING,
            "En attente de la décision DSIL",
        ),
        (
            PROJET_STATUS_DISMISSED,
            PROJET_STATUS_PROCESSING,
            "En attente de la décision DSIL",
        ),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_ACCEPTED,
            "En attente de la décision DETR",
        ),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_REFUSED,
            "En attente de la décision DETR",
        ),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_DISMISSED,
            "En attente de la décision DETR",
        ),
    ),
)
def test_projet_detail_page_has_correct_notification_status_message_when_no_notification_date_has_been_set(
    dotation_status_1, dotation_status_2, notification_status_message
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(perimetre=perimetre)

    dotation_projet_detr = DotationProjetFactory(
        projet=projet, status=dotation_status_1, dotation=DOTATION_DETR
    )
    if dotation_status_1 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_detr, status=dotation_status_1
        )

    dotation_projet_dsil = DotationProjetFactory(
        projet=projet, status=dotation_status_2, dotation=DOTATION_DSIL
    )
    if dotation_status_2 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_dsil, status=dotation_status_2
        )

    url = reverse(
        "gsl_projet:get-projet",
        kwargs={"projet_id": projet.id},
    )
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    if notification_status_message == "À notifier":
        assert projet.to_notify is True
        assert projet.notified_at is None

    assert response.context["projet"].all_dotations_have_processing_status is False
    assert notification_status_message in response.content.decode()


@pytest.mark.parametrize(
    "dotation_status_1, dotation_status_2, notification_status_message",
    (
        (
            PROJET_STATUS_ACCEPTED,
            PROJET_STATUS_ACCEPTED,
            "Notifié",
        ),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, "Notifié"),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, "Notifié"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, "Notifié"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, "Notifié"),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, "Notifié"),
        # These cases should not exist =>
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, "Notifié"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING, "Notifié"),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING, "Notifié"),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED, "Notifié"),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_REFUSED, "Notifié"),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_DISMISSED, "Notifié"),
    ),
)
def test_projet_detail_page_has_correct_notification_status_message_when_already_notified(
    dotation_status_1, dotation_status_2, notification_status_message
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(perimetre=perimetre, notified_at=datetime.now())

    dotation_projet_detr = DotationProjetFactory(
        projet=projet, status=dotation_status_1, dotation=DOTATION_DETR
    )
    if dotation_status_1 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_detr, status=dotation_status_1
        )

    dotation_projet_dsil = DotationProjetFactory(
        projet=projet, status=dotation_status_2, dotation=DOTATION_DSIL
    )
    if dotation_status_2 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_dsil, status=dotation_status_2
        )

    url = reverse(
        "gsl_projet:get-projet",
        kwargs={"projet_id": projet.id},
    )
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    assert projet.to_notify is False
    assert projet.notified_at is not None
    assert response.context["projet"].all_dotations_have_processing_status is False
    assert notification_status_message in response.content.decode()

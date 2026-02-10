from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import (
    DetrProjetFactory,
    DotationProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_simulation.views.simulation_projet_views import (
    _get_other_dotation_montants,
)

pytestmark = pytest.mark.django_db


def test_get_other_dotation_montants_without_double_dotations():
    """Test that function returns None when projet doesn't have double dotations."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(projet=projet)
    simulation_projet = SimulationProjetFactory(dotation_projet=dsil_dotation_projet)

    result = _get_other_dotation_montants(simulation_projet)

    assert result is None


def test_get_other_dotation_montants_dsil_to_detr_without_programmation():
    """Test DSIL -> DETR direction when other dotation has no programmation."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("10000.00")
    )
    DetrProjetFactory(projet=projet, assiette=Decimal("20000.00"))
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("5000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DETR
    assert result["assiette"] == Decimal("20000.00")
    assert result["montant"] is None
    assert result["taux"] is None


def test_get_other_dotation_montants_detr_to_dsil_without_programmation():
    """Test DETR -> DSIL direction when other dotation has no programmation."""
    projet = ProjetFactory()
    detr_dotation_projet = DetrProjetFactory(
        projet=projet, assiette=Decimal("15000.00")
    )
    DsilProjetFactory(projet=projet, assiette=Decimal("25000.00"))
    simulation_projet = SimulationProjetFactory(
        dotation_projet=detr_dotation_projet, montant=Decimal("8000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DSIL
    assert result["assiette"] == Decimal("25000.00")
    assert result["montant"] is None
    assert result["taux"] is None


def test_get_other_dotation_montants_dsil_to_detr_with_programmation():
    """Test DSIL -> DETR direction when other dotation has programmation."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("10000.00")
    )
    detr_dotation_projet = DetrProjetFactory(
        projet=projet, assiette=Decimal("20000.00")
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=detr_dotation_projet, montant=Decimal("15000.00")
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("5000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DETR
    assert result["assiette"] == Decimal("20000.00")
    assert result["montant"] == Decimal("15000.00")
    assert result["taux"] == programmation_projet.taux


def test_get_other_dotation_montants_detr_to_dsil_with_programmation():
    """Test DETR -> DSIL direction when other dotation has programmation."""
    projet = ProjetFactory()
    detr_dotation_projet = DetrProjetFactory(
        projet=projet, assiette=Decimal("15000.00")
    )
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("25000.00")
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("20000.00")
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=detr_dotation_projet, montant=Decimal("8000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DSIL
    assert result["assiette"] == Decimal("25000.00")
    assert result["montant"] == Decimal("20000.00")
    assert result["taux"] == programmation_projet.taux


def test_get_other_dotation_montants_with_none_assiette():
    """Test that function handles None assiette correctly."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("10000.00")
    )
    DetrProjetFactory(projet=projet, assiette=None)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("5000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DETR
    assert result["assiette"] is None
    assert result["montant"] is None
    assert result["taux"] is None


@pytest.mark.parametrize(
    "status",
    (
        SimulationProjet.STATUS_PROCESSING,
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_DISMISSED,
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
    ),
)
def test_status_and_notification_status_card_is_displayed_everytime(status):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dotation_projet = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation, dotation_projet=dotation_projet, status=status
    )
    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )
    assert response.status_code == 200
    assert "Décision de financement du projet" in response.content.decode()
    assert 'aria-label="Options de statut"' in response.content.decode(), (
        f"Status dropdown is always displayed for status {status}"
    )


@pytest.mark.parametrize("dotation", (DOTATION_DSIL, DOTATION_DETR))
def test_status_and_notification_status_card_is_displayed_with_the_correct_title(
    dotation,
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dotation_projet = DotationProjetFactory(projet=projet, dotation=dotation)
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation, dotation_projet=dotation_projet
    )
    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )
    assert response.status_code == 200
    assert f"Décision de financement du projet {dotation}" in response.content.decode()


@pytest.mark.parametrize(
    "dotation_status, simulation_projet_status, must_be_displayed",
    (
        (PROJET_STATUS_ACCEPTED, SimulationProjet.STATUS_ACCEPTED, True),
        (PROJET_STATUS_REFUSED, SimulationProjet.STATUS_REFUSED, True),
        (PROJET_STATUS_DISMISSED, SimulationProjet.STATUS_DISMISSED, True),
        (PROJET_STATUS_PROCESSING, SimulationProjet.STATUS_PROCESSING, False),
        (
            PROJET_STATUS_PROCESSING,
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
            False,
        ),
        (
            PROJET_STATUS_PROCESSING,
            SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
            False,
        ),
    ),
)
def test_status_and_notification_status_card_displays_the_notification_status_or_not_with_simple_dotation(
    dotation_status,
    simulation_projet_status,
    must_be_displayed,
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_status
    )
    enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet,
        status=simulation_projet_status,
    )
    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )
    assert response.status_code == 200
    if must_be_displayed:
        assert (
            '<div class="fr-callout__text notification_status_message'
            in response.content.decode()
        )
    else:
        assert (
            '<div class="fr-callout__text notification_status_message'
            not in response.content.decode()
        )


DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS = {
    PROJET_STATUS_ACCEPTED: SimulationProjet.STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED: SimulationProjet.STATUS_REFUSED,
    PROJET_STATUS_DISMISSED: SimulationProjet.STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING: SimulationProjet.STATUS_PROCESSING,
}


@pytest.mark.parametrize(
    "dotation_1_status, dotation_2_status, must_be_displayed",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_PROCESSING, False),
    ),
)
def test_status_and_notification_status_card_displays_the_notification_status_or_not_with_double_dotations(
    dotation_1_status, dotation_2_status, must_be_displayed
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dotation_projet_1 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_1_status
    )
    _dotation_projet_2 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_2_status
    )
    enveloppe_1 = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe_1)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet_1,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_1_status],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    if must_be_displayed:
        assert (
            '<div class="fr-callout__text notification_status_message'
            in response.content.decode()
        )
    else:
        assert (
            '<div class="fr-callout__text notification_status_message'
            not in response.content.decode()
        )


@pytest.mark.parametrize(
    "dotation_1_status, dotation_2_status, notification_status_message",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED, "À notifier"),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, "À notifier"),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, "À notifier"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, "À notifier"),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, "À notifier"),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, "À notifier"),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_ACCEPTED,
            "En attente de la décision DSIL",
        ),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_REFUSED,
            "En attente de la décision DSIL",
        ),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_DISMISSED,
            "En attente de la décision DSIL",
        ),
    ),
)
def test_status_and_notification_status_card_displays_the_correct_notification_status_message(
    dotation_1_status, dotation_2_status, notification_status_message
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dotation_projet_1 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_1_status
    )
    if dotation_1_status is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_1, status=dotation_1_status
        )
    dotation_projet_2 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_2_status
    )
    if dotation_2_status is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_2, status=dotation_2_status
        )
    enveloppe_1 = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe_1)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet_1,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_1_status],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    assert notification_status_message in response.content.decode()


@pytest.mark.parametrize(
    "dotation_1_status, dotation_2_status",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED),
        # These statuses configurations should not exist when the projet has been notified =>
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_PROCESSING),
    ),
)
@pytest.mark.parametrize(
    "notified_at,notification_status_message",
    (
        (None, "À notifier"),
        (datetime.now(timezone.utc), "Notifié"),
    ),
)
def test_status_and_notification_status_card_displays_the_correct_notification_status_message_depending_on_the_notified_at_date(
    dotation_1_status, dotation_2_status, notified_at, notification_status_message
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre, notified_at=notified_at)
    dotation_projet_1 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_1_status
    )
    if dotation_1_status is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_1, status=dotation_1_status
        )

    dotation_projet_2 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_2_status
    )
    if dotation_2_status is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_2, status=dotation_2_status
        )

    enveloppe_1 = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe_1)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet_1,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_1_status],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    if (
        dotation_1_status == PROJET_STATUS_PROCESSING
        and dotation_2_status == PROJET_STATUS_PROCESSING
    ):
        assert projet.all_dotations_have_processing_status is True
        assert projet.display_notification_message is False
        assert (
            'div class="fr-callout__text notification_status_message'
            not in response.content.decode()
        )
        return

    if notified_at is None:
        if any(
            status == PROJET_STATUS_PROCESSING
            for status in (dotation_1_status, dotation_2_status)
        ):
            assert projet.all_dotations_have_processing_status is False
            assert projet.display_notification_message is True
            notification_status_message = "En attente de la décision"

    assert notification_status_message in response.content.decode()


@pytest.mark.parametrize(
    "dotation_status, is_button_displayed",
    (
        (PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_PROCESSING, False),
        # These statuses configurations should not exist when the projet has not been notified =>
        (PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_DISMISSED, False),
    ),
)
def test_status_and_notification_status_card_displays_notification_button_simple_dotation_when_the_projet_has_not_been_notified(
    dotation_status, is_button_displayed
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre, notified_at=None)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_status
    )
    if dotation_status is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet, status=dotation_status
        )
    enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_status],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    if is_button_displayed:
        assert 'id="to_notify_button"' in response.content.decode()
        assert "Notifier le demandeur" in response.content.decode()
    else:
        assert 'id="to_notify_button"' not in response.content.decode()
        assert "Notifier le demandeur" not in response.content.decode()


@pytest.mark.parametrize(
    "dotation_status",
    (
        (PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_REFUSED),
        (PROJET_STATUS_DISMISSED),
        (PROJET_STATUS_PROCESSING),
    ),
)
def test_status_and_notification_status_card_does_not_display_notification_button_simple_dotation_when_the_projet_has_been_notified(
    dotation_status,
):
    """
    When the projet has been notified, the notification button should not be displayed.
    """
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(
        dossier_ds__perimetre=perimetre, notified_at=datetime.now(timezone.utc)
    )
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_status
    )
    if dotation_status is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet, status=dotation_status
        )
    enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_status],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    assert 'id="to_notify_button"' not in response.content.decode()
    assert "Notifier le demandeur" not in response.content.decode()


@pytest.mark.parametrize(
    "dotation_status_1, dotation_status_2, is_button_displayed",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_PROCESSING, False),
    ),
)
def test_status_and_notification_status_card_displays_notification_button_double_dotation_when_the_projet_has_not_been_notified(
    dotation_status_1, dotation_status_2, is_button_displayed
):
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre, notified_at=None)
    dotation_projet_1 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_status_1
    )
    if dotation_status_1 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_1, status=dotation_status_1
        )
    dotation_projet_2 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_status_2
    )
    if dotation_status_2 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_2, status=dotation_status_2
        )
    enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet_1,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_status_1],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    if is_button_displayed:
        assert 'id="to_notify_button"' in response.content.decode()
        assert "Notifier le demandeur" in response.content.decode()
    else:
        assert 'id="to_notify_button"' not in response.content.decode()
        assert "Notifier le demandeur" not in response.content.decode()


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
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_REFUSED),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_DISMISSED),
    ),
)
def test_status_and_notification_status_card_does_not_display_notification_button_double_dotation_when_the_projet_has_been_notified(
    dotation_status_1,
    dotation_status_2,
):
    """
    When the projet has been notified, the notification button should not be displayed.
    """
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    projet = ProjetFactory(
        dossier_ds__perimetre=perimetre, notified_at=datetime.now(timezone.utc)
    )
    dotation_projet_1 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=dotation_status_1
    )
    if dotation_status_1 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_1, status=dotation_status_1
        )
    dotation_projet_2 = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_status_2
    )
    if dotation_status_2 is not PROJET_STATUS_PROCESSING:
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_2, status=dotation_status_2
        )
    enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    simulation = SimulationFactory(enveloppe=enveloppe)
    simulation_projet = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet_1,
        status=DOTATION_PROJET_STATUS_TO_SIMULATION_PROJET_STATUS[dotation_status_1],
    )

    response = client.get(
        reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.pk}
        )
    )

    assert response.status_code == 200
    assert 'id="to_notify_button"' not in response.content.decode()
    assert "Notifier le demandeur" not in response.content.decode()


class TestNotifiedProjectDisplayOnDetailPage:
    """Tests for display of notified projects on detail page (text instead of forms)"""

    def test_notified_project_shows_text_instead_of_dotation_form(self):
        """
        Notified projects should show dotation as text instead of checkbox form
        """
        perimetre = PerimetreArrondissementFactory()
        collegue = CollegueFactory(perimetre=perimetre)
        client = ClientWithLoggedUserFactory(user=collegue)

        projet = ProjetFactory(
            dossier_ds__perimetre=perimetre,
            notified_at=datetime.now(tz=timezone.utc),
        )
        dotation_projet = DetrProjetFactory(projet=projet)
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            simulation=simulation, dotation_projet=dotation_projet
        )

        response = client.get(
            reverse(
                "simulation:simulation-projet-detail",
                kwargs={"pk": simulation_projet.pk},
            )
        )

        assert response.status_code == 200
        content = response.content.decode()
        # Should NOT have the dotation checkbox form
        assert 'id="dotation-fieldset"' not in content
        # Should show dotation as text
        assert "Dispositif" in content
        assert "DETR" in content

    def test_notified_project_shows_text_instead_of_montant_form(self):
        """
        Notified projects should show montant as text instead of input form
        """
        perimetre = PerimetreArrondissementFactory()
        collegue = CollegueFactory(perimetre=perimetre)
        client = ClientWithLoggedUserFactory(user=collegue)

        projet = ProjetFactory(
            dossier_ds__perimetre=perimetre,
            notified_at=datetime.now(tz=timezone.utc),
        )
        dotation_projet = DetrProjetFactory(projet=projet, assiette=10_000)
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            simulation=simulation, dotation_projet=dotation_projet, montant=5_000
        )

        response = client.get(
            reverse(
                "simulation:simulation-projet-detail",
                kwargs={"pk": simulation_projet.pk},
            )
        )

        assert response.status_code == 200
        content = response.content.decode()
        # Should NOT have the montant form
        assert 'id="simulation_projet_form"' not in content
        # Should show "Montant accordé" text (from dotation_montant_info.html)
        assert "Montant accordé" in content

    def test_non_notified_project_shows_forms(self):
        """
        Non-notified projects should still show editable forms
        """
        perimetre = PerimetreArrondissementFactory()
        collegue = CollegueFactory(perimetre=perimetre)
        client = ClientWithLoggedUserFactory(user=collegue)

        projet = ProjetFactory(dossier_ds__perimetre=perimetre, notified_at=None)
        dotation_projet = DetrProjetFactory(projet=projet)
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            simulation=simulation, dotation_projet=dotation_projet
        )

        response = client.get(
            reverse(
                "simulation:simulation-projet-detail",
                kwargs={"pk": simulation_projet.pk},
            )
        )

        assert response.status_code == 200
        content = response.content.decode()
        # Should have the dotation checkbox form
        assert 'id="dotation-fieldset"' in content
        # Should have the montant form
        assert 'id="simulation_projet_form"' in content

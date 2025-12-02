import pytest

from gsl_core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    (
        "create_a_detr_projet",
        "create_a_dsil_projet",
        "demande_montant",
        "expected_can_have_a_commission_detr_avis",
    ),
    (
        (True, False, 100_000, True),
        (True, False, 99_999, False),
        (True, False, None, False),
        (True, True, 100_000, True),
        (True, True, 99_999, False),
        (True, True, None, False),
        (False, True, 100_000, False),
        (False, True, 99_999, False),
        (False, True, None, False),
    ),
)
def test_can_have_a_commission_detr_avis(
    create_a_detr_projet,
    create_a_dsil_projet,
    demande_montant,
    expected_can_have_a_commission_detr_avis,
):
    projet = ProjetFactory(dossier_ds__demande_montant=demande_montant)
    if create_a_detr_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    if create_a_dsil_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    assert (
        projet.can_have_a_commission_detr_avis
        is expected_can_have_a_commission_detr_avis
    )


def test_has_double_dotations():
    projet = ProjetFactory()
    assert projet.has_double_dotations is False

    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.has_double_dotations is False

    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.has_double_dotations is True


def test_dotation_detr():
    projet = ProjetFactory()
    assert projet.dotation_detr is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.dotation_detr is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.dotation_detr == dotation


def test_dotation_dsil():
    projet = ProjetFactory()
    assert projet.dotation_dsil is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.dotation_dsil is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.dotation_dsil == dotation


def test_to_notify_false_without_programmation():
    """Project without any programmation should return False."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert projet.to_notify is False


def test_to_notify_true_with_programmation_not_notified():
    """Project with programmation but not notified should return True."""
    projet = ProjetFactory()
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    ProgrammationProjetFactory(dotation_projet=dotation)
    assert projet.to_notify is True


def test_to_notify_false_when_projet_already_notified():
    """Project already notified should return False."""
    from django.utils import timezone

    projet = ProjetFactory(notified_at=timezone.now())
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    ProgrammationProjetFactory(dotation_projet=dotation)
    assert projet.to_notify is False


def test_to_notify_with_double_dotation_all_notified():
    """Double dotation project returns False only if all dotations are notified."""
    from django.utils import timezone

    projet = ProjetFactory(notified_at=timezone.now())
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    ProgrammationProjetFactory(dotation_projet=dotation_detr)
    ProgrammationProjetFactory(dotation_projet=dotation_dsil)

    assert projet.to_notify is False


def test_to_notify_with_double_dotation_partial_programmation():
    """Double dotation project returns False if any dotation lacks programmation."""
    projet = ProjetFactory()
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    # Only create programmation for DETR
    ProgrammationProjetFactory(dotation_projet=dotation_detr)

    assert projet.to_notify is False


def test_with_at_least_one_programmed_dotation():
    """Project with at least one programmated dotation should return True."""
    projet = ProjetFactory()
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(dotation_projet=dotation)
    assert Projet.objects.with_at_least_one_programmed_dotation().count() == 1


def test_with_at_least_one_programmed_dotation_without_programmation():
    """Project without programmated dotation should return False."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert Projet.objects.with_at_least_one_programmed_dotation().count() == 0


def test_with_at_least_one_programmed_dotation_when_projet_has_two_programmated_dotations():
    """Project without programmated dotation should return False."""
    projet = ProjetFactory()
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    ProgrammationProjetFactory(dotation_projet=dotation_detr)
    ProgrammationProjetFactory(dotation_projet=dotation_dsil)
    assert Projet.objects.with_at_least_one_programmed_dotation().count() == 1


def test_for_user_and_at_least_one_programmated_dotation():
    perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(perimetre=perimetre)
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(dotation_projet=dotation_detr)

    projet_not_in_perimeter = ProjetFactory()
    dotation_detr_not_in_perimeter = DotationProjetFactory(
        projet=projet_not_in_perimeter, dotation=DOTATION_DETR
    )
    ProgrammationProjetFactory(dotation_projet=dotation_detr_not_in_perimeter)

    assert (
        Projet.objects.for_user(user).with_at_least_one_programmed_dotation().count()
        == 1
    )


def test_can_display_notification_tab_without_dotations():
    """Project without any dotations should return False."""
    projet = ProjetFactory()
    assert projet.can_display_notification_tab is False


def test_can_display_notification_tab_with_accepted_dotation():
    """Project with processing dotation should return False."""
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    assert projet.can_display_notification_tab is True


@pytest.mark.parametrize(
    "dotation_status",
    [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING],
)
def test_can_display_notification_tab_with_not_accepted_dotation(dotation_status):
    """Project with not accepted dotation should return False."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=dotation_status)
    assert projet.can_display_notification_tab is False


@pytest.mark.parametrize(
    "first_dotation_status, second_dotation_status, expected_can_display_notification_tab",
    [
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_PROCESSING, False),
    ],
)
def test_can_display_notification_tab_with_multiple_dotations(
    first_dotation_status, second_dotation_status, expected_can_display_notification_tab
):
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=first_dotation_status
    )
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=second_dotation_status
    )
    assert projet.can_display_notification_tab is expected_can_display_notification_tab


def test_dotation_not_treated_without_dotations():
    """Project without any dotations should return None."""
    projet = ProjetFactory()
    assert projet.dotation_not_treated is None


def test_dotation_not_treated_with_processing_dotation():
    """Project with processing dotation should return that dotation."""
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    assert projet.dotation_not_treated == DOTATION_DETR


@pytest.mark.parametrize(
    "dotation_status",
    [PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED],
)
def test_dotation_not_treated_with_not_processing_dotation(dotation_status):
    """Project with non-processing dotation should return None."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=dotation_status)
    assert projet.dotation_not_treated is None


@pytest.mark.parametrize(
    "first_status, second_status, expected_dotation_not_treated",
    [
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, DOTATION_DSIL),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED, DOTATION_DETR),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_PROCESSING,
            DOTATION_DETR,
        ),  # Should return the first one encountered (DETR)
    ],
)
def test_dotation_not_treated_with_multiple_dotations_one_processing(
    first_status, second_status, expected_dotation_not_treated
):
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=first_status)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL, status=second_status)
    assert projet.dotation_not_treated == expected_dotation_not_treated

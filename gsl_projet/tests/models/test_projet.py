import pytest

from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
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

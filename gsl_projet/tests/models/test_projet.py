import pytest

from gsl_programmation.models import ProgrammationProjet
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


@pytest.mark.parametrize(
    "status, notified_at, expected",
    (
        (ProgrammationProjet.STATUS_ACCEPTED, None, True),
        (ProgrammationProjet.STATUS_ACCEPTED, "2023-01-01", False),
        (ProgrammationProjet.STATUS_REFUSED, None, False),
        (ProgrammationProjet.STATUS_REFUSED, "2023-01-01", False),
    ),
)
@pytest.mark.django_db
def test_to_notify_true_and_false(status, notified_at, expected):
    projet = ProjetFactory()
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    assert projet.to_notify is False

    ProgrammationProjetFactory(
        dotation_projet=dotation,
        status=status,
        notified_at=notified_at,
    )
    assert projet.to_notify is expected

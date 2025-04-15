import pytest

from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_montant_retenu_with_accepted_programmation_projet():
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, montant=10_000
    )
    projet = programmation_projet.projet
    projet.accepted_programmation_projets = [programmation_projet]
    assert projet.montant_retenu == 10_000


def test_montant_retenu_with_refused_programmation_projet():
    projet = ProjetFactory()
    assert projet.montant_retenu is None

    ProgrammationProjetFactory(
        projet=projet, status=ProgrammationProjet.STATUS_REFUSED, montant=0
    )
    assert projet.montant_retenu is None


def test_taux_retenu_with_accepted_programmation_projet():
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, taux=10
    )
    projet = programmation_projet.projet
    projet.accepted_programmation_projets = [programmation_projet]
    assert projet.taux_retenu == 10


def test_taux_retenu_with_refused_programmation_projet():
    projet = ProjetFactory()
    assert projet.taux_retenu is None

    ProgrammationProjetFactory(
        projet=projet, status=ProgrammationProjet.STATUS_REFUSED, taux=0
    )
    assert projet.taux_retenu is None


@pytest.mark.parametrize(
    ("create_a_detr_projet", "create_a_dsil_projet", "expected_is_asking_for_detr"),
    (
        (True, False, True),
        (True, True, True),
        (False, True, False),
    ),
)
def test_is_asking_for_detr(
    create_a_detr_projet, create_a_dsil_projet, expected_is_asking_for_detr
):
    projet = ProjetFactory()
    if create_a_detr_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    if create_a_dsil_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    assert projet.is_asking_for_detr is expected_is_asking_for_detr

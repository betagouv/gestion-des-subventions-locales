from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db


def test_i_cannot_create_two_prog_for_the_same_projet_enveloppe():
    first_prog_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    with pytest.raises(IntegrityError):
        ProgrammationProjetFactory(
            projet=first_prog_projet.projet,
            enveloppe=first_prog_projet.enveloppe,
            status=ProgrammationProjet.STATUS_REFUSED,
        )


def test_i_can_accept_a_project_on_two_different_enveloppes():
    first_prog_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, enveloppe=DetrEnveloppeFactory()
    )
    ProgrammationProjetFactory(
        projet=first_prog_projet.projet,
        enveloppe=DsilEnveloppeFactory(annee=first_prog_projet.enveloppe.annee),
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )


def test_taux_consistency_is_checked():
    projet = ProjetFactory(assiette=Decimal("1234.00"))
    prog_projet = ProgrammationProjetFactory(
        projet=projet, montant=Decimal("42"), taux=Decimal("10.00")
    )
    with pytest.raises(ValidationError) as exc_info:
        prog_projet.full_clean()

    exception_message = exc_info.value.message_dict["__all__"][0]
    assert "Taux attendu : 3.4" in exception_message

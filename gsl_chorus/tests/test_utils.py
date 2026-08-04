from decimal import Decimal

import pytest

from gsl_chorus.models import SuiviFinancier
from gsl_chorus.utils import build_suivi_par_dotation
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.tests.factories import (
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)

DS_NUMBER = 28281965


def make_projet_with_accorde(dotation_factory, montant):
    projet = ProjetFactory(dossier_ds=DossierFactory(ds_number=DS_NUMBER))
    dotation_projet = dotation_factory(projet=projet)
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=Decimal(montant),
    )
    return projet


def make_ligne(dotation, montant, type_montant="0100", dn=DS_NUMBER):
    return SuiviFinancier.objects.create(
        ej="2105003612",
        dn=dn,
        dotation=dotation,
        montant=Decimal(montant),
        type_montant=type_montant,
    )


@pytest.mark.django_db
def test_engage_paye_reste_computed():
    projet = make_projet_with_accorde(DetrProjetFactory, "12000")
    make_ligne("DETR", "10000", type_montant="0100")
    make_ligne("DETR", "3000", type_montant="0250")
    make_ligne("DETR", "-1000", type_montant="0200")

    (groupe,) = build_suivi_par_dotation(projet)
    assert groupe["dotation"] == "DETR"
    assert groupe["engage"] == Decimal("12000")
    assert groupe["paye"] == Decimal("3000")
    assert groupe["reste"] == Decimal("9000")
    assert groupe["accorde"] == Decimal("12000")
    assert groupe["ecart"] is False


@pytest.mark.django_db
def test_ecart_flagged_when_engage_differs_from_accorde():
    projet = make_projet_with_accorde(DetrProjetFactory, "5000")
    make_ligne("DETR", "6000")

    (groupe,) = build_suivi_par_dotation(projet)
    assert groupe["accorde"] == Decimal("5000")
    assert groupe["engage"] == Decimal("6000")
    assert groupe["ecart"] is True


@pytest.mark.django_db
def test_paye_counts_0250_and_0260():
    projet = make_projet_with_accorde(DetrProjetFactory, "5000")
    make_ligne("DETR", "2000", type_montant="0250")
    make_ligne("DETR", "1000", type_montant="0260")
    make_ligne("DETR", "500", type_montant="0100")

    (groupe,) = build_suivi_par_dotation(projet)
    assert groupe["paye"] == Decimal("3000")


@pytest.mark.django_db
def test_only_dotations_with_lignes_are_returned():
    projet = make_projet_with_accorde(DetrProjetFactory, "5000")
    make_ligne("DETR", "5000")

    result = build_suivi_par_dotation(projet)
    assert [g["dotation"] for g in result] == ["DETR"]


@pytest.mark.django_db
def test_lignes_of_other_projet_are_excluded():
    projet = make_projet_with_accorde(DetrProjetFactory, "5000")
    make_ligne("DETR", "5000")
    make_ligne("DETR", "9999", dn=11111111)

    (groupe,) = build_suivi_par_dotation(projet)
    assert groupe["engage"] == Decimal("5000")


@pytest.mark.django_db
def test_accorde_none_when_no_programmation_for_that_dotation():
    projet = make_projet_with_accorde(DetrProjetFactory, "5000")
    DsilProjetFactory(projet=projet)
    make_ligne("DETR", "5000")
    make_ligne("DSIL", "3000")

    result = {g["dotation"]: g for g in build_suivi_par_dotation(projet)}
    assert result["DSIL"]["accorde"] is None
    assert result["DSIL"]["ecart"] is False

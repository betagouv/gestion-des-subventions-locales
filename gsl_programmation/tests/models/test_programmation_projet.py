import re
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from gsl_core.models import Perimetre
from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.mark.parametrize(
    "montant, assiette, finance_cout_total, expected_taux",
    (
        (1_000, 2_000, 4_000, 50),
        (1_000, 2_000, None, 50),
        (1_000, None, 4_000, 25),
        (1_000, None, None, 0),
    ),
)
@pytest.mark.django_db
def test_progammation_projet_taux(montant, assiette, finance_cout_total, expected_taux):
    dotation_projet = DotationProjetFactory(
        assiette=assiette, projet__dossier_ds__finance_cout_total=finance_cout_total
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=dotation_projet, montant=montant
    )
    assert isinstance(programmation_projet.taux, Decimal)
    assert programmation_projet.taux == expected_taux


@pytest.mark.django_db
def test_two_programmation_projets_cant_have_the_same_dotation_projet():
    dotation_projet = DotationProjetFactory()
    ProgrammationProjetFactory(dotation_projet=dotation_projet)

    with pytest.raises(IntegrityError) as exc_info:
        ProgrammationProjetFactory(dotation_projet=dotation_projet)
    assert (
        'duplicate key value violates unique constraint "gsl_programmation_progra_dotation_projet_id_ab0086eb_uniq"'
        in str(exc_info.value)
    )
    assert re.search(
        "DETAIL:  Key \(dotation_projet_id\)=\(\d+\) already exists.",
        str(exc_info.value),
    )


@pytest.mark.django_db
def test_programmation_projet_cant_have_a_montant_higher_than_projet_assiette():
    dotation_projet = DotationProjetFactory(
        assiette=100, projet__dossier_ds__finance_cout_total=200
    )
    with pytest.raises(ValidationError) as exc_info:
        pp = ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=101)
        pp.full_clean()
    assert (
        "Le montant de la programmation ne peut pas être supérieur à l'assiette du projet pour cette dotation."
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_programmation_projet_cant_have_a_montant_higher_than_projet_cout_total():
    dotation_projet = DotationProjetFactory(projet__dossier_ds__finance_cout_total=100)
    with pytest.raises(ValidationError) as exc_info:
        pp = ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=101)
        pp.full_clean()
    assert (
        "Le montant de la programmation ne peut pas être supérieur au coût total du projet pour cette dotation."
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_i_can_accept_a_project_on_two_different_enveloppes():
    projet_detr = DotationProjetFactory(dotation=DOTATION_DETR)
    projet_dsil = DotationProjetFactory(
        dotation=DOTATION_DSIL, projet=projet_detr.projet
    )
    first_prog_projet = ProgrammationProjetFactory(
        dotation_projet=projet_detr,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=DetrEnveloppeFactory(),
    )
    ProgrammationProjetFactory(
        dotation_projet=projet_dsil,
        enveloppe=DsilEnveloppeFactory(annee=first_prog_projet.enveloppe.annee),
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )


@pytest.fixture
def arrondisement_perimetre() -> Perimetre:
    return PerimetreArrondissementFactory()


@pytest.fixture
def projet(arrondisement_perimetre) -> Projet:
    return ProjetFactory(perimetre=arrondisement_perimetre)


@pytest.fixture
def dotation_projet(projet) -> DotationProjet:
    return DotationProjetFactory(
        projet=projet, assiette=Decimal("1234.00"), dotation=DOTATION_DSIL
    )


@pytest.fixture
def region_perimetre(arrondisement_perimetre) -> Perimetre:
    return PerimetreRegionalFactory(region=arrondisement_perimetre.region)


@pytest.fixture
def enveloppe(region_perimetre) -> Enveloppe:
    return DsilEnveloppeFactory(perimetre=region_perimetre)


@pytest.fixture
def departement_perimetre(arrondisement_perimetre) -> Perimetre:
    return PerimetreRegionalFactory(
        departement=arrondisement_perimetre.departement,
        region=arrondisement_perimetre.region,
    )


@pytest.fixture
def enveloppe_deleguee(enveloppe, departement_perimetre) -> Enveloppe:
    return DsilEnveloppeFactory(deleguee_by=enveloppe, perimetre=departement_perimetre)


@pytest.mark.django_db
def test_clean_programmation_on_deleguee_enveloppe(dotation_projet, enveloppe_deleguee):
    programmation = ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        enveloppe=enveloppe_deleguee,
        montant=Decimal("100.00"),
    )
    with pytest.raises(ValidationError) as exc_info:
        programmation.clean()
    assert (
        "Une programmation ne peut pas être faite sur une enveloppe déléguée."
        in exc_info.value.message_dict["enveloppe"][0]
    )


@pytest.mark.django_db
def test_clean_valid_programmation(dotation_projet, enveloppe):
    programmation = ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        enveloppe=enveloppe,
        montant=Decimal("100.00"),
    )
    programmation.clean()


@pytest.mark.django_db
def test_clean_programmation_with_refused_status(dotation_projet, enveloppe):
    programmation = ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        enveloppe=enveloppe,
        montant=Decimal("100.00"),
        status=ProgrammationProjet.STATUS_REFUSED,
    )
    with pytest.raises(ValidationError) as exc_info:
        programmation.clean()
    errors = exc_info.value.message_dict
    assert "Un projet refusé doit avoir un montant nul." in str(errors["montant"])


@pytest.mark.django_db
def test_programmation_projet_with_a_projet_not_in_enveloppe_perimetre_must_raise_an_error():
    dotation_projet = DotationProjetFactory(dotation=DOTATION_DSIL)
    enveloppe = DsilEnveloppeFactory()
    pp = ProgrammationProjetFactory(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )

    with pytest.raises(ValidationError) as exc_info:
        pp.clean()

    assert (
        "Le périmètre de l'enveloppe ne contient pas le périmètre du projet."
        in exc_info.value.message_dict.get("enveloppe")[0]
    )


@pytest.mark.django_db
def test_programmation_projet_with_an_enveloppe_dotation_different_from_dotation_projet_one():
    enveloppe = DsilEnveloppeFactory()
    dotation_projet = DotationProjetFactory(dotation=DOTATION_DETR)
    pp = ProgrammationProjetFactory(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )

    with pytest.raises(ValidationError) as exc_info:
        pp.clean()

    assert (
        "La dotation de l'enveloppe ne correspond pas à celle du projet pour cette dotation."
        in exc_info.value.message_dict.get("enveloppe")[0]
    )


@pytest.mark.django_db
def test_programmation_projet_with_a_projet_in_enveloppe_perimetre_must_be_okay():
    projet_perimetre = PerimetreArrondissementFactory()
    enveloppe_perimetre = PerimetreRegionalFactory(region=projet_perimetre.region)
    dotation_projet = DotationProjetFactory(
        projet__perimetre=projet_perimetre, dotation=DOTATION_DSIL
    )
    enveloppe = DsilEnveloppeFactory(perimetre=enveloppe_perimetre)

    pp = ProgrammationProjetFactory(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )

    pp.full_clean()

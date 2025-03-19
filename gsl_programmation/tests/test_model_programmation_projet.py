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
from gsl_projet.models import Projet
from gsl_projet.tests.factories import ProjetFactory


@pytest.mark.django_db
def test_programmation_projet_cant_have_a_montant_higher_than_projet_assiette():
    projet = ProjetFactory(assiette=100, dossier_ds__finance_cout_total=200)
    with pytest.raises(ValidationError) as exc_info:
        pp = ProgrammationProjetFactory.build(projet=projet, montant=101)
        pp.full_clean()
    assert (
        "Le montant de la programmation ne peut pas être supérieur à l'assiette du projet."
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_programmation_projet_cant_have_a_montant_higher_than_projet_cout_total():
    projet = ProjetFactory(dossier_ds__finance_cout_total=100)
    with pytest.raises(ValidationError) as exc_info:
        pp = ProgrammationProjetFactory(projet=projet, montant=101)
        pp.full_clean()
    assert (
        "Le montant de la programmation ne peut pas être supérieur au coût total du projet."
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_programmation_projet_cant_have_a_taux_higher_than_100():
    with pytest.raises(ValidationError) as exc_info:
        pp = ProgrammationProjetFactory(taux=101)
        pp.full_clean()
    assert (
        "Le taux de la programmation ne peut pas être supérieur à 100."
        in exc_info.value.message_dict.get("taux")[0]
    )


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_i_can_accept_a_project_on_two_different_enveloppes():
    first_prog_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, enveloppe=DetrEnveloppeFactory()
    )
    ProgrammationProjetFactory(
        projet=first_prog_projet.projet,
        enveloppe=DsilEnveloppeFactory(annee=first_prog_projet.enveloppe.annee),
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )


@pytest.fixture
def arrondisement_perimetre() -> Perimetre:
    return PerimetreArrondissementFactory()


@pytest.fixture
def projet(arrondisement_perimetre) -> Projet:
    return ProjetFactory(assiette=Decimal("1234.00"), perimetre=arrondisement_perimetre)


@pytest.mark.django_db
def test_taux_consistency_is_valid_with_a_difference_of_more_than_a_tenth(
    projet, enveloppe
):
    for taux in [Decimal("3.39"), Decimal("3.42")]:
        prog_projet = ProgrammationProjetFactory.build(
            projet=projet, montant=Decimal("42"), taux=taux, enveloppe=enveloppe
        )
        with pytest.raises(ValidationError) as exc_info:
            prog_projet.full_clean()

        exception_message = exc_info.value.message_dict["taux"][0]
        assert (
            "Le taux et le montant de la programmation ne sont pas cohérents."
            in exception_message
        )
        assert "Taux attendu : 3.40" in exception_message


@pytest.mark.django_db
def test_taux_consistency_is_valid_with_a_difference_of_less_than_a_tenth(
    projet, enveloppe
):
    for taux in [Decimal("3.40"), Decimal("3.41")]:
        prog_projet = ProgrammationProjetFactory.build(
            projet=projet, montant=Decimal("42"), taux=taux, enveloppe=enveloppe
        )
        prog_projet.full_clean()


@pytest.fixture
def region_perimetre(arrondisement_perimetre) -> Perimetre:
    return PerimetreRegionalFactory(region=arrondisement_perimetre.region)


@pytest.fixture
def departement_perimetre(arrondisement_perimetre) -> Perimetre:
    return PerimetreRegionalFactory(
        departement=arrondisement_perimetre.departement,
        region=arrondisement_perimetre.region,
    )


@pytest.fixture
def enveloppe(region_perimetre) -> Enveloppe:
    return DsilEnveloppeFactory(perimetre=region_perimetre)


@pytest.fixture
def enveloppe_deleguee(enveloppe, departement_perimetre) -> Enveloppe:
    return DsilEnveloppeFactory(deleguee_by=enveloppe, perimetre=departement_perimetre)


@pytest.mark.django_db
def test_clean_programmation_on_deleguee_enveloppe(projet, enveloppe_deleguee):
    programmation = ProgrammationProjetFactory.build(
        projet=projet,
        enveloppe=enveloppe_deleguee,
        montant=Decimal("100.00"),
        taux=Decimal("8.10"),
    )
    with pytest.raises(ValidationError) as exc_info:
        programmation.clean()
    assert (
        "Une programmation ne peut pas être faite sur une enveloppe déléguée."
        in exc_info.value.message_dict["enveloppe"][0]
    )


@pytest.mark.django_db
def test_clean_valid_programmation(projet, enveloppe):
    programmation = ProgrammationProjetFactory.build(
        projet=projet,
        enveloppe=enveloppe,
        montant=Decimal("100.00"),
        taux=Decimal("8.10"),
    )
    programmation.clean()


@pytest.mark.django_db
def test_clean_programmation_with_refused_status(projet, enveloppe):
    programmation = ProgrammationProjetFactory.build(
        projet=projet,
        enveloppe=enveloppe,
        montant=Decimal("100.00"),
        taux=Decimal("8.10"),
        status=ProgrammationProjet.STATUS_REFUSED,
    )
    with pytest.raises(ValidationError) as exc_info:
        programmation.clean()
    errors = exc_info.value.message_dict
    assert "Un projet refusé doit avoir un montant nul." in str(errors["montant"])
    assert "Un projet refusé doit avoir un taux nul." in str(errors["taux"])


@pytest.mark.django_db
def test_programmation_projet_with_a_projet_not_in_enveloppe_perimetre_must_raise_an_error():
    projet = ProjetFactory()
    enveloppe = DsilEnveloppeFactory()
    pp = ProgrammationProjetFactory.build(projet=projet, enveloppe=enveloppe)

    with pytest.raises(ValidationError) as exc_info:
        pp.clean()

    assert (
        "Le périmètre de l'enveloppe ne contient pas le périmètre du projet."
        in exc_info.value.message_dict.get("enveloppe")[0]
    )


@pytest.mark.django_db
def test_programmation_projet_with_a_projet_in_enveloppe_perimetre_must_be_okay():
    projet_perimetre = PerimetreArrondissementFactory()
    enveloppe_perimetre = PerimetreRegionalFactory(region=projet_perimetre.region)
    projet = ProjetFactory(perimetre=projet_perimetre)
    enveloppe = DsilEnveloppeFactory(perimetre=enveloppe_perimetre)

    pp = ProgrammationProjetFactory.build(projet=projet, enveloppe=enveloppe)

    pp.full_clean()

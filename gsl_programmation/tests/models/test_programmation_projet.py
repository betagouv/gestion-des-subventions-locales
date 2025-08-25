import re
from datetime import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from gsl_core.models import Perimetre
from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteEtLettreSignesFactory,
    ArreteFactory,
    LettreNotificationFactory,
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


@pytest.mark.django_db
class TestProgrammationProjetQuerySet:
    def test_for_enveloppe_with_non_delegated_enveloppe(self):
        enveloppe = DetrEnveloppeFactory(deleguee_by=None)

        programmation_projet_1 = ProgrammationProjetFactory(enveloppe=enveloppe)
        programmation_projet_2 = ProgrammationProjetFactory(enveloppe=enveloppe)
        other_programmation_projet = ProgrammationProjetFactory()

        result = ProgrammationProjet.objects.for_enveloppe(enveloppe)

        assert programmation_projet_1 in result
        assert programmation_projet_2 in result
        assert other_programmation_projet not in result
        assert result.count() == 2

    def test_for_enveloppe_with_delegated_enveloppe(self):
        """Test de for_enveloppe avec une enveloppe déléguée DETR"""
        # Créer un périmètre départemental et un périmètre d'arrondissement
        perimetre_arrondissement = PerimetreArrondissementFactory()
        perimetre_departement = PerimetreDepartementalFactory(
            departement=perimetre_arrondissement.departement
        )

        # Créer une enveloppe mère (départementale)
        enveloppe_mere = DetrEnveloppeFactory(
            perimetre=perimetre_departement, deleguee_by=None
        )

        # Créer une enveloppe déléguée (arrondissement)
        enveloppe_deleguee = DetrEnveloppeFactory(
            perimetre=perimetre_arrondissement, deleguee_by=enveloppe_mere
        )

        # Créer des projets programmés
        # Projet dans l'arrondissement, programmé sur l'enveloppe mère
        projet_arrondissement = ProjetFactory(perimetre=perimetre_arrondissement)
        dotation_projet_arrondissement = DotationProjetFactory(
            projet=projet_arrondissement, dotation=DOTATION_DETR
        )
        programmation_projet_arrondissement = ProgrammationProjetFactory(
            dotation_projet=dotation_projet_arrondissement, enveloppe=enveloppe_mere
        )

        # Projet dans un autre arrondissement, programmé sur l'enveloppe mère
        autre_arrondissement = PerimetreArrondissementFactory(
            arrondissement__departement=perimetre_departement.departement,
            departement=perimetre_departement.departement,
        )
        projet_autre_arrondissement = ProjetFactory(perimetre=autre_arrondissement)
        dotation_projet_autre = DotationProjetFactory(
            projet=projet_autre_arrondissement, dotation=DOTATION_DETR
        )
        programmation_projet_autre = ProgrammationProjetFactory(
            dotation_projet=dotation_projet_autre, enveloppe=enveloppe_mere
        )

        # Tester la méthode for_enveloppe avec l'enveloppe déléguée
        result = ProgrammationProjet.objects.for_enveloppe(enveloppe_deleguee)

        # Vérifier que seuls les projets du périmètre de l'enveloppe déléguée sont retournés
        assert programmation_projet_arrondissement in result
        assert programmation_projet_autre not in result
        assert result.count() == 1

    def test_for_enveloppe_with_dsil_delegated_enveloppe(self):
        """Test de for_enveloppe avec une enveloppe déléguée DSIL"""
        perimetre_arrondissement = PerimetreArrondissementFactory()
        perimetre_departement = PerimetreDepartementalFactory(
            departement=perimetre_arrondissement.departement,
            region=perimetre_arrondissement.region,
        )
        perimetre_region = PerimetreRegionalFactory(
            region=perimetre_arrondissement.region
        )

        # Création d'une enveloppe mère et une enveloppe déléguée
        enveloppe_mere = DsilEnveloppeFactory(
            perimetre=perimetre_region, deleguee_by=None
        )
        enveloppe_deleguee = DsilEnveloppeFactory(
            perimetre=perimetre_departement, deleguee_by=enveloppe_mere
        )
        assert (
            perimetre_arrondissement.departement
            == enveloppe_deleguee.perimetre.departement
        )

        # Création d'un projet au niveau départemental
        projet_departement = ProjetFactory(perimetre=perimetre_departement)
        dotation_projet_departement = DotationProjetFactory(
            projet=projet_departement, dotation=DOTATION_DSIL
        )
        programmation_projet_departement = ProgrammationProjetFactory(
            dotation_projet=dotation_projet_departement, enveloppe=enveloppe_mere
        )

        # Création d'un projet au niveau d'arrondissement
        projet_arrondissement = ProjetFactory(perimetre=perimetre_arrondissement)
        dotation_projet_arrondissement = DotationProjetFactory(
            projet=projet_arrondissement, dotation=DOTATION_DSIL
        )
        programmation_projet_arrondissement = ProgrammationProjetFactory(
            dotation_projet=dotation_projet_arrondissement, enveloppe=enveloppe_mere
        )

        # Création d'un projet dans un autre département
        autre_departement = PerimetreDepartementalFactory(
            departement__region=perimetre_departement.region,
            region=perimetre_departement.region,
        )
        projet_autre = ProjetFactory(perimetre=autre_departement)
        dotation_projet_autre = DotationProjetFactory(
            projet=projet_autre, dotation=DOTATION_DSIL
        )
        ProgrammationProjetFactory(
            dotation_projet=dotation_projet_autre, enveloppe=enveloppe_mere
        )

        # Test de la méthode for_enveloppe avec l'enveloppe déléguée
        result = ProgrammationProjet.objects.for_enveloppe(enveloppe_deleguee)

        assert programmation_projet_departement in result
        assert programmation_projet_arrondissement in result
        assert result.count() == 2

    def test_to_notify(self):
        accepted_and_no_notified_at = ProgrammationProjetFactory(
            status=ProgrammationProjet.STATUS_ACCEPTED, notified_at=None
        )
        _accepted_and_notified_at = ProgrammationProjetFactory(
            status=ProgrammationProjet.STATUS_ACCEPTED, notified_at=datetime.now()
        )
        _refused_and_no_notified_at = ProgrammationProjetFactory(
            status=ProgrammationProjet.STATUS_REFUSED, notified_at=None
        )
        _refused_and_notified_at = ProgrammationProjetFactory(
            status=ProgrammationProjet.STATUS_REFUSED, notified_at=datetime.now()
        )

        result = ProgrammationProjet.objects.to_notify()

        assert accepted_and_no_notified_at in result
        assert result.count() == 1


@pytest.mark.django_db
def test_documents_summary_no_document():
    programmation_projet = ProgrammationProjetFactory()
    assert programmation_projet.documents_summary == []


@pytest.mark.django_db
def test_documents_summary_arrete_genere():
    programmation_projet = ProgrammationProjetFactory()
    ArreteFactory(programmation_projet=programmation_projet)
    LettreNotificationFactory(programmation_projet=programmation_projet)

    summary = programmation_projet.documents_summary
    assert summary == ["1 arrêté généré", "1 lettre générée"]


@pytest.mark.parametrize(
    "annexes_count, expected_summary", ((0, []), (1, ["1 annexe"]), (2, ["2 annexes"]))
)
@pytest.mark.django_db
def test_documents_summary_annexes(annexes_count, expected_summary):
    programmation_projet = ProgrammationProjetFactory()
    AnnexeFactory.create_batch(annexes_count, programmation_projet=programmation_projet)

    summary = programmation_projet.documents_summary
    assert summary == expected_summary


@pytest.mark.django_db
def test_documents_summary_arrete_et_lettre_signes_hides_arrete_and_lettre_generes():
    programmation_projet = ProgrammationProjetFactory()
    ArreteEtLettreSignesFactory(programmation_projet=programmation_projet)
    ArreteFactory(programmation_projet=programmation_projet)
    LettreNotificationFactory(programmation_projet=programmation_projet)

    summary = programmation_projet.documents_summary
    assert summary == ["1 arrêté et lettre signés"]

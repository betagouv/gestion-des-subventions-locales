import re

import pytest
from django.shortcuts import reverse

from dn.sync.models import Cofinancement
from dn.sync.tests.factories import CategorieDetrFactory, CategorieDsilFactory
from gsl.core.tests.factories import ClientWithLoggedUserFactory, CollegueFactory
from gsl.programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl.projet.constants import ProjetStatus
from gsl.projet.tests.factories import (
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)

pytestmark = pytest.mark.django_db()


def test_dotations_tab_is_displayed_between_projet_and_notes_tabs():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    url = reverse("gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id})

    response = ClientWithLoggedUserFactory(user=user).get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert re.search(rf'href="{url}[^"]*"\s+aria-selected="true"', content)
    assert (
        content.index(">Projet</a>")
        < content.index(">Dotations</a>")
        < content.index(">Notes</a>")
    )


def test_dotations_tab_is_not_accessible_outside_perimetre():
    projet = ProjetFactory()
    url = reverse("gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id})

    response = ClientWithLoggedUserFactory(user=CollegueFactory()).get(url)

    assert response.status_code == 404


def test_dotations_tab_displays_financement_and_autres_dotations_sollicitees():
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre,
        dossier_ds__finance_cout_total=150_000,
        dossier_ds__demande_montant=100_000,
    )
    projet.dossier_ds.demande_cofinancements.add(
        Cofinancement.objects.create(label="Fonds vert"),
        Cofinancement.objects.create(label="Dotation politique de la ville (DPV)"),
    )
    url = reverse("gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id})

    response = ClientWithLoggedUserFactory(user=user).get(url)

    content = response.content.decode()
    assert "Coût total de l’opération : 150\xa0000\xa0€" in content
    assert "Montant total sollicité : 100\xa0000\xa0€" in content
    assert "<li>Fonds vert</li>" in content
    assert "<li>Dotation politique de la ville (DPV)</li>" in content


def test_dotations_tab_without_autres_dotations_sollicitees():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    url = reverse("gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id})

    response = ClientWithLoggedUserFactory(user=user).get(url)

    assert "<p>Aucune</p>" in response.content.decode()


def _get_dotations_tab_text(user, projet):
    url = reverse("gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id})
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    return " ".join(re.sub(r"<[^>]+>", " ", response.content.decode()).split())


def test_dotation_card_displays_financial_informations_of_a_programmed_dotation():
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre,
        dossier_ds__demande_montant=80_000,
        dossier_ds__demande_categorie_detr=CategorieDetrFactory(
            label="Améliorer les espaces scolaires"
        ),
    )
    DetrProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        assiette=100_000,
        montant=50_000,
        enveloppe=DetrEnveloppeFactory(perimetre=user.perimetre, annee=2026),
    )

    text = _get_dotations_tab_text(user, projet)

    assert "DETR - 2026" in text
    assert "Catégorie d'opération DETR : Améliorer les espaces scolaires" in text
    assert "Assiette subventionnable : 100 000 €" in text
    assert "Taux de subvention sollicité : 80" in text
    assert "Montant retenu : 50 000 €" in text
    assert "Taux retenu : 50" in text


def test_dotation_card_hides_financial_informations_of_a_dotation_in_processing():
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre,
        dossier_ds__demande_categorie_dsil=CategorieDsilFactory(label="Rénovation"),
    )
    DsilProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DsilEnveloppeFactory(perimetre=user.perimetre, annee=2027),
    )

    text = _get_dotations_tab_text(user, projet)

    assert "DSIL - 2027" in text
    assert "Catégorie d'opération DSIL : Rénovation" in text
    assert "Assiette subventionnable" not in text
    assert "Montant retenu" not in text


@pytest.mark.parametrize(
    "status,avis,expected",
    (
        (ProjetStatus.REFUSED, False, "Avis de la commission Non"),
        (ProjetStatus.ACCEPTED, True, "Avis de la commission Oui"),
        (ProjetStatus.PROCESSING, True, None),
    ),
)
def test_dotation_card_displays_detr_avis_commission_of_a_programmed_dotation(
    status, avis, expected
):
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    DetrProjetFactory(projet=projet, status=status, detr_avis_commission=avis)

    text = _get_dotations_tab_text(user, projet)

    if expected:
        assert expected in text
    else:
        assert "Avis de la commission" not in text


def test_dotation_card_does_not_display_avis_commission_for_dsil():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    DsilProjetFactory(projet=projet, status=ProjetStatus.ACCEPTED)

    assert "Avis de la commission" not in _get_dotations_tab_text(user, projet)

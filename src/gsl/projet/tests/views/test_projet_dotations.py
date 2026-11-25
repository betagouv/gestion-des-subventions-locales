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


def _get_dotations_tab_content(user, projet):
    url = reverse("gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id})
    response = ClientWithLoggedUserFactory(user=user).get(url)
    assert response.status_code == 200
    return response.content.decode()


def _get_dotations_tab_text(user, projet):
    content = _get_dotations_tab_content(user, projet)
    return " ".join(re.sub(r"<[^>]+>", " ", content).split())


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
    assert "Assiette subventionnable :" not in text
    assert "Montant retenu" not in text


def _dotation_card_form_url(enveloppe_projet):
    return reverse(
        "fragment:gsl_projet:dotation_card_form", kwargs={"pk": enveloppe_projet.pk}
    )


@pytest.mark.parametrize(
    "status,avis,expected",
    (
        (ProjetStatus.REFUSED, False, "Avis de la commission Non"),
        (ProjetStatus.ACCEPTED, True, "Avis de la commission Oui"),
        (ProjetStatus.DISMISSED, None, "Avis de la commission En cours"),
    ),
)
def test_programmed_dotation_card_displays_detr_avis_commission_read_only(
    status, avis, expected
):
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre, dossier_ds__demande_montant=100_000
    )
    enveloppe_projet = DetrProjetFactory(
        projet=projet, status=status, detr_avis_commission=avis
    )

    content = _get_dotations_tab_content(user, projet)

    assert expected in " ".join(re.sub(r"<[^>]+>", " ", content).split())
    assert _dotation_card_form_url(enveloppe_projet) not in content


def test_processing_detr_dotation_card_has_a_single_form_with_avis_and_assiette():
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre, dossier_ds__demande_montant=100_000
    )
    enveloppe_projet = DetrProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DetrEnveloppeFactory(perimetre=user.perimetre, annee=2026),
    )

    content = _get_dotations_tab_content(user, projet)

    assert content.count(_dotation_card_form_url(enveloppe_projet)) == 1
    assert 'name="detr_avis_commission"' in content
    assert 'name="assiette"' in content
    assert content.count(">\n        Enregistrer\n    </button>") == 1
    assert "Assiette subventionnable" in content
    assert (
        "Cette valeur est identique sur toutes les simulations de cette dotation."
        in content
    )
    # The card already displays the dotation title: the form does not repeat it.
    assert content.count("DETR - 2026") == 1


@pytest.mark.parametrize("demande_montant", (99_999, None))
def test_processing_detr_dotation_card_form_has_no_avis_below_min_demande_montant(
    demande_montant,
):
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre,
        dossier_ds__demande_montant=demande_montant,
    )
    DetrProjetFactory(projet=projet, status=ProjetStatus.PROCESSING)

    content = _get_dotations_tab_content(user, projet)

    assert 'name="assiette"' in content
    assert 'name="detr_avis_commission"' not in content
    assert "Avis de la commission" not in content


@pytest.mark.parametrize("status", (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED))
def test_programmed_detr_dotation_card_has_no_avis_below_min_demande_montant(status):
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre, dossier_ds__demande_montant=99_999
    )
    DetrProjetFactory(projet=projet, status=status)

    assert "Avis de la commission" not in _get_dotations_tab_content(user, projet)


@pytest.mark.parametrize("status", (ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED))
def test_dsil_dotation_card_has_no_avis_commission(status):
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre, dossier_ds__demande_montant=100_000
    )
    DsilProjetFactory(projet=projet, status=status)

    content = _get_dotations_tab_content(user, projet)

    assert "Avis de la commission" not in content
    assert 'name="detr_avis_commission"' not in content


@pytest.mark.parametrize(
    "status", (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED)
)
def test_programmed_dotation_card_has_no_form(status):
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    enveloppe_projet = DsilProjetFactory(projet=projet, status=status)

    content = _get_dotations_tab_content(user, projet)

    assert _dotation_card_form_url(enveloppe_projet) not in content
    assert 'name="assiette"' not in content


def test_dotation_card_form_saves_assiette_and_detr_avis_commission():
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre, dossier_ds__demande_montant=100_000
    )
    enveloppe_projet = DetrProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        assiette=10_000,
        detr_avis_commission=None,
    )
    url = _dotation_card_form_url(enveloppe_projet)

    response = ClientWithLoggedUserFactory(user=user).post(
        url,
        {"assiette": "50 000 €", "detr_avis_commission": "False"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.assiette == 50_000
    assert enveloppe_projet.detr_avis_commission is False
    content = response.content.decode()
    assert url in content
    assert "Modifications enregistrées" in content


def test_dotation_card_form_ignores_detr_avis_commission_for_dsil():
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre, dossier_ds__demande_montant=100_000
    )
    enveloppe_projet = DsilProjetFactory(
        projet=projet, status=ProjetStatus.PROCESSING, detr_avis_commission=None
    )

    ClientWithLoggedUserFactory(user=user).post(
        _dotation_card_form_url(enveloppe_projet),
        {"assiette": "50000", "detr_avis_commission": "True"},
        headers={"HX-Request": "true"},
    )

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.assiette == 50_000
    assert enveloppe_projet.detr_avis_commission is None


def test_dotation_card_form_requires_assiette():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    enveloppe_projet = DsilProjetFactory(
        projet=projet, status=ProjetStatus.PROCESSING, assiette=10_000
    )

    response = ClientWithLoggedUserFactory(user=user).post(
        _dotation_card_form_url(enveloppe_projet),
        {"assiette": ""},
        headers={"HX-Request": "true"},
    )

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.assiette == 10_000
    content = response.content.decode()
    assert "fr-input-group--error" in content
    assert "Modifications enregistrées" not in content


@pytest.mark.parametrize(
    "status", (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED)
)
def test_dotation_card_form_cannot_be_posted_for_a_programmed_dotation(status):
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    enveloppe_projet = DsilProjetFactory(projet=projet, status=status)

    response = ClientWithLoggedUserFactory(user=user).post(
        _dotation_card_form_url(enveloppe_projet),
        {"assiette": "50000"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404

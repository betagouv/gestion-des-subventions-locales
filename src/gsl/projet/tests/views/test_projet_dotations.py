import re

import pytest
from django.contrib.messages import get_messages
from django.shortcuts import reverse

from dn.sync.models import Cofinancement, Dotation
from dn.sync.tests.factories import CategorieDetrFactory, CategorieDsilFactory
from gsl.core.tests.factories import ClientWithLoggedUserFactory, CollegueFactory
from gsl.historique.models import ProjetAction
from gsl.programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl.projet.constants import ProjetStatus
from gsl.projet.models import EnveloppeProjet
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
    assert "Catégorie d'opération : Améliorer les espaces scolaires" in text
    assert "Assiette subventionnable : 100 000 €" in text
    assert "Taux de subvention sollicité : 80" in text
    assert "Montant retenu : 50 000 €" in text
    assert "Taux retenu : 50" in text


def test_dotation_card_hides_retained_amounts_of_a_dotation_in_processing():
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
    assert "Catégorie d'opération : Rénovation" in text
    assert "Montant retenu" not in text
    assert "Taux retenu" not in text


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


def _get_dotation_card_fragment(user, enveloppe_projet, edit=False):
    url = _dotation_card_form_url(enveloppe_projet)
    if edit:
        url += "?edit"
    return ClientWithLoggedUserFactory(user=user).get(
        url, headers={"HX-Request": "true"}
    )


def _processing_detr_enveloppe_projet(user, **kwargs):
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre,
        dossier_ds__demande_montant=100_000,
        dossier_ds__finance_cout_total=400_000,
    )
    return DetrProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DetrEnveloppeFactory(perimetre=user.perimetre, annee=2026),
        **kwargs,
    )


def test_processing_detr_dotation_card_is_read_only_with_a_modify_button():
    user = CollegueFactory()
    enveloppe_projet = _processing_detr_enveloppe_projet(
        user, assiette=200_000, detr_avis_commission=True
    )

    content = _get_dotations_tab_content(user, enveloppe_projet.projet)
    text = _get_dotations_tab_text(user, enveloppe_projet.projet)

    assert "Avis de la commission Oui" in text
    assert "Assiette subventionnable : 200 000 €" in text
    assert "Taux de subvention sollicité : 50,00 %" in text
    assert f'hx-get="{_dotation_card_form_url(enveloppe_projet)}?edit"' in content
    assert re.search(r">\s*Modifier\s*</button>", content)
    assert 'name="assiette"' not in content
    assert 'name="detr_avis_commission"' not in content
    assert "Enregistrer" not in content
    # The card already displays the dotation title: the fragment does not repeat it.
    assert content.count("DETR - 2026") == 1


def test_modify_button_opens_the_dotation_card_form():
    user = CollegueFactory()
    enveloppe_projet = _processing_detr_enveloppe_projet(user)

    response = _get_dotation_card_fragment(user, enveloppe_projet, edit=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert f'hx-post="{_dotation_card_form_url(enveloppe_projet)}"' in content
    assert 'name="detr_avis_commission"' in content
    assert 'name="assiette"' in content
    assert "autofocus" in content
    assert "Assiette subventionnable" in content
    assert (
        "Cette valeur est identique sur toutes les simulations de cette dotation."
        in content
    )
    assert re.search(r">\s*Enregistrer\s*</button>", content)
    assert f'hx-get="{_dotation_card_form_url(enveloppe_projet)}"' in content
    assert re.search(r">\s*Annuler\s*</button>", content)
    assert "Modifier" not in content


def test_cancel_button_brings_the_dotation_card_back_to_read_only():
    user = CollegueFactory()
    enveloppe_projet = _processing_detr_enveloppe_projet(user)

    response = _get_dotation_card_fragment(user, enveloppe_projet)

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="assiette"' not in content
    assert re.search(r">\s*Modifier\s*</button>", content)


@pytest.mark.parametrize("demande_montant", (99_999, None))
def test_processing_detr_dotation_card_has_no_avis_below_min_demande_montant(
    demande_montant,
):
    user = CollegueFactory()
    projet = ProjetFactory(
        dossier_ds__perimetre=user.perimetre,
        dossier_ds__demande_montant=demande_montant,
    )
    enveloppe_projet = DetrProjetFactory(projet=projet, status=ProjetStatus.PROCESSING)

    assert "Avis de la commission" not in _get_dotations_tab_content(user, projet)
    content = _get_dotation_card_fragment(
        user, enveloppe_projet, edit=True
    ).content.decode()
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
    text = " ".join(re.sub(r"<[^>]+>", " ", content).replace("\xa0", " ").split())
    assert "Modifications enregistrées" in text
    assert "Assiette subventionnable : 50 000 €" in text
    assert "Avis de la commission Non" in text
    assert 'name="assiette"' not in content
    assert f'hx-get="{url}?edit"' in content


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
    assert 'name="assiette"' in content


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


@pytest.mark.parametrize("edit", (True, False))
def test_dotation_card_fragment_cannot_be_fetched_for_a_programmed_dotation(edit):
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    enveloppe_projet = DsilProjetFactory(projet=projet, status=ProjetStatus.ACCEPTED)

    response = _get_dotation_card_fragment(user, enveloppe_projet, edit=edit)

    assert response.status_code == 404


def _delete_url(enveloppe_projet):
    return reverse(
        "gsl_projet:enveloppe-projet-delete", kwargs={"pk": enveloppe_projet.pk}
    )


def _projet_with_detr_and_dsil(user, detr_status=ProjetStatus.PROCESSING):
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    detr = DetrProjetFactory(projet=projet, status=detr_status)
    dsil = DsilProjetFactory(projet=projet, status=ProjetStatus.PROCESSING)
    return projet, detr, dsil


def test_dotation_card_displays_delete_action_with_its_confirmation_modal():
    user = CollegueFactory()
    projet, detr, _ = _projet_with_detr_and_dsil(user)

    content = _get_dotations_tab_content(user, projet)

    assert _delete_url(detr) in content
    assert f'aria-controls="delete-enveloppe-projet-modal-{detr.pk}"' in content
    assert f'id="delete-enveloppe-projet-modal-{detr.pk}"' in content
    assert f'form="delete-enveloppe-projet-form-{detr.pk}"' in content


def test_dotation_card_hides_delete_action_of_the_only_enveloppe_projet():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    enveloppe_projet = DetrProjetFactory(projet=projet, status=ProjetStatus.PROCESSING)

    content = _get_dotations_tab_content(user, projet)

    assert _delete_url(enveloppe_projet) not in content


@pytest.mark.parametrize(
    "status", (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED)
)
def test_dotation_card_hides_delete_action_of_a_programmed_enveloppe_projet(status):
    user = CollegueFactory()
    projet, detr, dsil = _projet_with_detr_and_dsil(user, detr_status=status)

    content = _get_dotations_tab_content(user, projet)

    assert _delete_url(detr) not in content
    assert _delete_url(dsil) in content


def test_delete_enveloppe_projet():
    user = CollegueFactory()
    projet, detr, dsil = _projet_with_detr_and_dsil(user)

    response = ClientWithLoggedUserFactory(user=user).post(_delete_url(detr))

    assert response.status_code == 302
    assert response.url == reverse(
        "gsl_projet:get-projet-dotations", kwargs={"projet_id": projet.id}
    )
    assert list(EnveloppeProjet.all_objects.filter(projet=projet)) == [dsil]
    projet.refresh_from_db()
    assert projet.dotations_updated_in_app is True
    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == ProjetAction.TYPE_DOTATION_REMOVED
    assert action.dotation == Dotation.DETR
    assert action.actor == user
    assert action.source == ProjetAction.SOURCE_TURGOT
    messages = [str(m) for m in get_messages(response.wsgi_request)]
    assert messages == [
        f"La dotation DETR - {detr.enveloppe.annee} a bien été supprimée."
    ]


def test_cannot_delete_the_only_enveloppe_projet():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    enveloppe_projet = DetrProjetFactory(projet=projet, status=ProjetStatus.PROCESSING)

    response = ClientWithLoggedUserFactory(user=user).post(
        _delete_url(enveloppe_projet)
    )

    assert response.status_code == 302
    assert EnveloppeProjet.objects.filter(pk=enveloppe_projet.pk).exists()
    assert not ProjetAction.objects.filter(projet=projet).exists()
    messages = [str(m) for m in get_messages(response.wsgi_request)]
    assert len(messages) == 1


@pytest.mark.parametrize(
    "status", (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED)
)
def test_cannot_delete_a_programmed_enveloppe_projet(status):
    user = CollegueFactory()
    projet, detr, _ = _projet_with_detr_and_dsil(user, detr_status=status)

    ClientWithLoggedUserFactory(user=user).post(_delete_url(detr))

    assert EnveloppeProjet.objects.filter(pk=detr.pk).exists()


def test_cannot_delete_an_enveloppe_projet_outside_perimetre():
    projet, detr, _ = _projet_with_detr_and_dsil(CollegueFactory())

    response = ClientWithLoggedUserFactory(user=CollegueFactory()).post(
        _delete_url(detr)
    )

    assert response.status_code == 404
    assert EnveloppeProjet.objects.filter(pk=detr.pk).exists()


def test_delete_enveloppe_projet_get_is_not_allowed():
    user = CollegueFactory()
    _, detr, _ = _projet_with_detr_and_dsil(user)

    response = ClientWithLoggedUserFactory(user=user).get(_delete_url(detr))

    assert response.status_code == 405

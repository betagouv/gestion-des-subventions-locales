from decimal import Decimal

import pytest
from django.urls import reverse
from pytest_django.asserts import assertTemplateUsed

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.forms import ProjetNoteForm
from gsl_projet.tests.factories import (
    DotationProjetFactory,
    ProjetFactory,
    ProjetNoteFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def client_with_user_logged():
    user = CollegueFactory()
    return ClientWithLoggedUserFactory(user)


@pytest.mark.django_db
def test_simulation_list_url(client_with_user_logged):
    url = reverse("simulation:simulation-list")
    response = client_with_user_logged.get(url, follow=True)
    assert response.status_code == 200


@pytest.fixture
def enveloppe_departemental():
    return DetrEnveloppeFactory()


@pytest.fixture
def client_with_same_departement_perimetre(enveloppe_departemental):
    collegue = CollegueFactory(perimetre=enveloppe_departemental.perimetre)
    return ClientWithLoggedUserFactory(collegue)


@pytest.mark.parametrize(
    "route",
    (
        "simulation:simulation-detail",
        "simulation:simulation-projets-export",
    ),
)
@pytest.mark.django_db
def test_simulation_detail_url_with_not_authorized_user(
    client_with_user_logged, enveloppe_departemental, route
):
    SimulationFactory(slug="test-slug", enveloppe=enveloppe_departemental)

    url = reverse(route, kwargs={"slug": "test-slug"})
    response = client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "route",
    (
        "simulation:simulation-detail",
        "simulation:simulation-projets-export",
    ),
)
@pytest.mark.django_db
def test_simulation_detail_url_for_user_with_correct_perimetre(
    client_with_same_departement_perimetre, enveloppe_departemental, route
):
    SimulationFactory(slug="test-slug", enveloppe=enveloppe_departemental)

    url = reverse(route, kwargs={"slug": "test-slug"})
    response = client_with_same_departement_perimetre.get(url)
    assert response.status_code == 200


@pytest.fixture
def cote_d_or():
    return DepartementFactory()


@pytest.fixture
def cote_d_or_perimetre(cote_d_or):
    return PerimetreDepartementalFactory(departement=cote_d_or)


@pytest.fixture
def client_with_cote_d_or_user_logged(cote_d_or_perimetre):
    cote_dorien_collegue = CollegueFactory(perimetre=cote_d_or_perimetre)
    return ClientWithLoggedUserFactory(cote_dorien_collegue)


@pytest.fixture
def cote_dorien_simulation_projet(cote_d_or_perimetre):
    dotation_projet = DotationProjetFactory(
        projet__perimetre=cote_d_or_perimetre,
        projet__dossier_ds__finance_cout_total=500_000,
        dotation=DOTATION_DETR,
    )
    simulation = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=cote_d_or_perimetre)
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=0,
    )


expected_status_summary = {
    "cancelled": 0,
    "draft": 0,
    "notified": 0,
    "provisionally_accepted": 1,
    "provisionally_refused": 0,
    "valid": 0,
}


def get_client_with_referer(perimetre, referer):
    cote_dorien_collegue = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(
        cote_dorien_collegue,
        headers={
            "Referer": referer,
        },
    )


@pytest.mark.django_db
def test_patch_taux_simulation_projet_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(url, {"taux": "0.5"}, follow=True)
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("2500.00")
    assert response.context["filter_params"] == ""

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.taux == 0.5


@pytest.mark.django_db
def test_patch_taux_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"taux": "0.5"}, headers={"HX-Request": "true"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert (
        response.context["dotation_projet"]
        == cote_dorien_simulation_projet.dotation_projet
    )
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("2500.00")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.taux == 0.5


@pytest.mark.django_db
def test_patch_montant_simulation_projet_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"montant": "100"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("100")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.montant == 100


@pytest.mark.django_db
def test_patch_montant_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"montant": "100"}, headers={"HX-Request": "true"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("100")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.montant == 100


status_update_expected_status_summary = {
    "cancelled": 0,
    "draft": 0,
    "notified": 0,
    "provisionally_accepted": 0,
    "provisionally_refused": 0,
    "valid": 1,
}


@pytest.mark.django_db
def test_patch_status_simulation_projet_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"status": "valid"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == status_update_expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("0")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_patch_status_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"status": "valid"}, headers={"HX-Request": "true"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == status_update_expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("0")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_simulation_form_url(client_with_user_logged):
    url = reverse("simulation:simulation-form")
    response = client_with_user_logged.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_patch_projet_only_if_projet_is_included_in_user_perimetre(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(url, {"taux": "0.5"}, follow=True)
    assert response.status_code == 200

    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"montant": "400"}, follow=True
    )
    assert response.status_code == 200

    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"status": "valid"}, follow=True
    )
    assert response.status_code == 200


@pytest.fixture
def client_with_iconnais_user_logged():
    yonne = DepartementFactory()
    yonne_perimetre = PerimetreDepartementalFactory(departement=yonne)
    icaunais_collegue = CollegueFactory(perimetre=yonne_perimetre)
    return ClientWithLoggedUserFactory(icaunais_collegue)


@pytest.mark.django_db
def test_cant_patch_projet_only_if_projet_is_not_included_in_user_perimetre(
    client_with_iconnais_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.post(url, {"taux": "0.5"})
    assert response.status_code == 404

    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.post(url, {"montant": "400"})
    assert response.status_code == 404

    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.post(url, {"status": "valid"})
    assert response.status_code == 404


@pytest.fixture
def perimetre_bourgogne(cote_d_or):
    return PerimetreRegionalFactory(region=cote_d_or.region)


@pytest.fixture
def client_with_bourguignon_user_logged(perimetre_bourgogne):
    bourguignon_collegue = CollegueFactory(perimetre=perimetre_bourgogne)
    return ClientWithLoggedUserFactory(bourguignon_collegue)


PATCH_ROUTES_AND_DATA = (
    ("simulation:patch-simulation-projet-taux", {"taux": "0.5"}),
    ("simulation:patch-simulation-projet-montant", {"montant": "400"}),
    ("simulation:patch-simulation-projet-status", {"status": "valid"}),
    (
        "simulation:patch-projet",
        {"is_in_qpv": "on", "is_attached_to_a_crte": "on", "is_budget_vert": ""},
    ),
    ("simulation:patch-dotation-projet", {"detr_avis_commission": ""}),
)


@pytest.mark.parametrize(
    "route, data",
    PATCH_ROUTES_AND_DATA,
)
@pytest.mark.django_db
def test_regional_user_cant_patch_projet_if_simulation_projet_is_associated_to_detr_enveloppe(
    client_with_bourguignon_user_logged, cote_dorien_simulation_projet, route, data
):
    url = reverse(
        route,
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_bourguignon_user_logged.post(url, data)
    assert response.status_code == 404


@pytest.fixture
def cote_dorien_dsil_simulation_projet(cote_d_or_perimetre):
    dotation_projet = DotationProjetFactory(
        projet__perimetre=cote_d_or_perimetre, assiette=1_000, dotation=DOTATION_DSIL
    )
    simulation = SimulationFactory(
        enveloppe=DsilEnveloppeFactory(perimetre=cote_d_or_perimetre)
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
    )


@pytest.mark.parametrize("route, data", PATCH_ROUTES_AND_DATA)
@pytest.mark.django_db
def test_regional_user_can_patch_projet_if_simulation_projet_is_associated_to_dsil_enveloppe_and_in_its_perimetre(
    client_with_bourguignon_user_logged, cote_dorien_dsil_simulation_projet, route, data
):
    url = reverse(
        route,
        kwargs={"pk": cote_dorien_dsil_simulation_projet.pk},
    )
    response = client_with_bourguignon_user_logged.post(url, data, follow=True)
    assert response.status_code == 200


@pytest.fixture
def client_with_staff_user_logged():
    staff_user = CollegueFactory(is_staff=True)
    return ClientWithLoggedUserFactory(staff_user)


@pytest.mark.parametrize("route, data", PATCH_ROUTES_AND_DATA)
@pytest.mark.django_db
def test_patch_projet_allowed_for_staff_user(
    client_with_staff_user_logged, cote_dorien_simulation_projet, route, data
):
    url = reverse(
        route,
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_staff_user_logged.post(
        url,
        data,
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_get_simulation_projet_detail_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:simulation-projet-detail",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.get(url)
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_projet_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet


@pytest.mark.django_db
def test_post_simulation_projet_detail_url(
    cote_d_or_perimetre, cote_dorien_simulation_projet
):
    annotations_tab_url = reverse(
        "simulation:simulation-projet-tab",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "tab": "annotations"},
    )
    client = get_client_with_referer(cote_d_or_perimetre, annotations_tab_url)

    response = client.post(
        annotations_tab_url,
        {"title": "Titre de la note", "content": "Contenu de la note"},
        follow=True,
    )
    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_simulation/tab_simulation_projet/tab_annotations.html"
    )
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    # Specific context for the annotations tab
    assert response.context["projet_note_form"].__class__ == ProjetNoteForm
    notes = cote_dorien_simulation_projet.projet.notes
    assert notes.count() == 1
    assert response.context["projet_notes"].count() == 1
    assert response.context["projet_notes"].first().title == "Titre de la note"
    assert response.context["projet_notes"].first().content == "Contenu de la note"


@pytest.mark.django_db
def test_post_simulation_for_a_user_not_in_perimetre(
    client_with_iconnais_user_logged, cote_dorien_simulation_projet
):
    annotations_tab_url = reverse(
        "simulation:simulation-projet-tab",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "tab": "annotations"},
    )

    response = client_with_iconnais_user_logged.post(
        annotations_tab_url,
        {"title": "Titre de la note", "content": "Contenu de la note"},
        follow=True,
    )
    assert response.status_code == 404
    notes = cote_dorien_simulation_projet.projet.notes
    assert notes.count() == 0


@pytest.mark.parametrize(
    "tab_name,expected_template",
    (
        ("historique", "gsl_simulation/tab_simulation_projet/tab_historique.html"),
        ("annotations", "gsl_simulation/tab_simulation_projet/tab_annotations.html"),
    ),
)
@pytest.mark.django_db
def test_simulation_projet_detail_tabs_use_the_right_templates(
    client_with_cote_d_or_user_logged,
    cote_dorien_simulation_projet,
    tab_name,
    expected_template,
):
    url = reverse(
        "simulation:simulation-projet-tab",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "tab": tab_name},
    )
    response = client_with_cote_d_or_user_logged.get(url)
    assert response.status_code == 200
    assertTemplateUsed("gsl_simulation/simulation_projet_detail.html")
    assertTemplateUsed(expected_template)


@pytest.mark.django_db
def test_simulation_projet_detail_tabs_404_if_wrong_tab(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:simulation-projet-tab",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "tab": "toto"},
    )
    response = client_with_cote_d_or_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_simulation_projet_detail_url_with_perimetre_not_in_user_one(
    client_with_iconnais_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:simulation-projet-detail",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_redirection_with_referer_allowed(
    cote_d_or_perimetre, cote_dorien_simulation_projet
):
    client = get_client_with_referer(
        cote_d_or_perimetre,
        reverse(
            "simulation:simulation-projet-detail",
            kwargs={"pk": cote_dorien_simulation_projet.pk},
        ),
    )

    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client.post(url, {"status": "valid"}, follow=True)
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_projet_detail.html"


@pytest.mark.django_db
def test_redirection_with_referer_not_allowed(
    cote_d_or_perimetre, cote_dorien_simulation_projet
):
    client = get_client_with_referer(cote_d_or_perimetre, "http://localhost:8001/")
    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client.post(url, {"status": "valid"}, follow=True)
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"


@pytest.mark.django_db
@pytest.mark.parametrize("method", ("get", "post"))
@pytest.mark.parametrize(
    "is_note_creator, is_projet_in_user_perimetre, with_htmx, expected_status_code",
    (
        (True, True, True, 200),
        (False, True, True, 403),
        (True, False, True, 404),
        (False, False, True, 403),
        (True, True, False, 403),
        (False, True, False, 403),
        (True, False, False, 403),
        (False, False, False, 403),
    ),
)
def test_edit_projet_note_url(
    client_with_cote_d_or_user_logged,
    client_with_iconnais_user_logged,
    cote_dorien_simulation_projet,
    is_note_creator,
    is_projet_in_user_perimetre,
    with_htmx,
    expected_status_code,
    method,
):
    client = (
        client_with_cote_d_or_user_logged
        if is_projet_in_user_perimetre
        else client_with_iconnais_user_logged
    )
    projet = (
        cote_dorien_simulation_projet.projet
        if is_projet_in_user_perimetre
        else ProjetFactory()
    )
    creator = client.user if is_note_creator else CollegueFactory()
    user_note = ProjetNoteFactory(
        projet=projet,
        created_by=creator,
    )

    url = reverse(
        "simulation:get-edit-projet-note",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "note_id": user_note.id},
    )
    headers = {"HX-Request": "true"} if with_htmx else {}
    if method == "get":
        response = client.get(url, headers=headers)
    else:
        response = client.post(
            url, headers=headers, data={"title": "A", "content": "b"}, follow=True
        )

    assert response.status_code == expected_status_code


@pytest.mark.django_db
@pytest.mark.parametrize(
    "is_note_creator, is_projet_in_user_perimetre, with_htmx, expected_status_code",
    (
        (True, True, True, 200),
        (False, True, True, 200),
        (True, False, True, 404),
        (False, False, True, 404),
        (True, True, False, 403),
        (False, True, False, 403),
        (True, False, False, 404),
        (False, False, False, 404),
    ),
)
def test_get_note_card_url(
    client_with_cote_d_or_user_logged,
    client_with_iconnais_user_logged,
    cote_dorien_simulation_projet,
    is_note_creator,
    is_projet_in_user_perimetre,
    with_htmx,
    expected_status_code,
):
    client = (
        client_with_cote_d_or_user_logged
        if is_projet_in_user_perimetre
        else client_with_iconnais_user_logged
    )
    projet = (
        cote_dorien_simulation_projet.projet
        if is_projet_in_user_perimetre
        else ProjetFactory()
    )
    creator = client.user if is_note_creator else CollegueFactory()
    user_note = ProjetNoteFactory(
        projet=projet,
        created_by=creator,
    )

    url = reverse(
        "simulation:get-note-card",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "note_id": user_note.id},
    )
    headers = {"HX-Request": "true"} if with_htmx else {}
    response = client.get(url, headers=headers)
    assert response.status_code == expected_status_code

from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import (
    DotationProjetFactory,
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

    kwargs = (
        {"slug": "test-slug"}
        if route == "simulation:simulation-detail"
        else {"slug": "test-slug", "type": "xls"}
    )

    url = reverse(route, kwargs=kwargs)
    response = client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_simulation_detail_url_for_user_with_correct_perimetre(
    client_with_same_departement_perimetre, enveloppe_departemental
):
    SimulationFactory(title="Test slug", enveloppe=enveloppe_departemental)

    url = reverse("simulation:simulation-detail", kwargs={"slug": "test-slug"})
    response = client_with_same_departement_perimetre.get(url)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "export_type, response_code",
    (
        ("xls", 200),
        ("xlsx", 200),
        ("csv", 200),
        ("ods", 200),
        ("inconnu_au_bataillon", 400),
    ),
)
@pytest.mark.django_db
def test_simulation_export_url_for_user_with_correct_perimetre(
    client_with_same_departement_perimetre,
    enveloppe_departemental,
    export_type,
    response_code,
):
    SimulationFactory(title="Test slug", enveloppe=enveloppe_departemental)

    url = reverse(
        "simulation:simulation-projets-export",
        kwargs={"slug": "test-slug", "type": export_type},
    )
    response = client_with_same_departement_perimetre.get(url)
    assert response.status_code == response_code


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
        projet__dossier_ds__perimetre=cote_d_or_perimetre,
        projet__dossier_ds__finance_cout_total=1_000_000,
        dotation=DOTATION_DETR,
        assiette=500_000,
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
def test_edit_taux_get_returns_edit_form(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:edit-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert f'id="edit-taux-{cote_dorien_simulation_projet.pk}"' in content


@pytest.mark.django_db
def test_edit_taux_post_saves_value(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:edit-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"taux": "0.5"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("2500.00")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.taux == 0.5


@pytest.mark.django_db
def test_edit_montant_get_returns_edit_form(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:edit-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert f'id="edit-montant-{cote_dorien_simulation_projet.pk}"' in content


@pytest.mark.django_db
def test_edit_montant_post_saves_value(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:edit-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"montant": "100"}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
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
def test_patch_status_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged,
    cote_dorien_simulation_projet,
):
    page_url = reverse(
        "simulation:simulation-detail",
        kwargs={"slug": cote_dorien_simulation_projet.simulation.slug},
    )
    htmx_headers = {"HX-Request": "true", "HX-Request-URL": page_url}
    url = reverse(
        "simulation:simulation-projet-update-programmed-status",
        kwargs={
            "pk": cote_dorien_simulation_projet.pk,
            "status": SimulationProjet.STATUS_ACCEPTED,
        },
    )
    with mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    ) as mock_ds_update:
        mock_ds_update.return_value = None
        response = client_with_cote_d_or_user_logged.post(url, headers=htmx_headers)
    assert response.status_code == 200
    assert "HX-Redirect" in response.headers

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
        "simulation:edit-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(url, {"taux": "0.5"}, follow=True)
    assert response.status_code == 200

    url = reverse(
        "simulation:edit-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, {"montant": "400"}, follow=True
    )
    assert response.status_code == 200

    url = reverse(
        "simulation:simulation-projet-update-programmed-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "status": "valid"},
    )
    response = client_with_cote_d_or_user_logged.post(
        url, headers={"HX-Request": "true"}
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
        "simulation:edit-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.post(url, {"taux": "0.5"})
    assert response.status_code == 404

    url = reverse(
        "simulation:edit-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.post(url, {"montant": "400"})
    assert response.status_code == 404

    url = reverse(
        "simulation:simulation-projet-update-simulation-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk, "status": "valid"},
    )
    response = client_with_iconnais_user_logged.post(
        url, headers={"HX-Request": "true"}
    )
    assert response.status_code == 404


@pytest.fixture
def perimetre_bourgogne(cote_d_or):
    return PerimetreRegionalFactory(region=cote_d_or.region)


@pytest.fixture
def client_with_bourguignon_user_logged(perimetre_bourgogne):
    bourguignon_collegue = CollegueFactory(perimetre=perimetre_bourgogne)
    return ClientWithLoggedUserFactory(bourguignon_collegue)


PATCH_ROUTES_AND_DATA = (
    ("simulation:edit-taux", {}, {"taux": "0.5"}),
    ("simulation:edit-montant", {}, {"montant": "400"}),
    (
        "simulation:simulation-projet-update-programmed-status",
        {"status": "valid"},
        None,
    ),
)


@pytest.mark.parametrize(
    "route, kwargs, data",
    PATCH_ROUTES_AND_DATA,
)
@pytest.mark.django_db
def test_regional_user_cant_patch_projet_if_simulation_projet_is_associated_to_detr_enveloppe(
    client_with_bourguignon_user_logged,
    cote_dorien_simulation_projet,
    route,
    kwargs,
    data,
):
    page_url = reverse(
        "simulation:simulation-detail",
        kwargs={"slug": cote_dorien_simulation_projet.simulation.slug},
    )
    url = reverse(
        route,
        kwargs={"pk": cote_dorien_simulation_projet.pk, **kwargs},
    )
    response = client_with_bourguignon_user_logged.post(
        url,
        data,
        headers={"HX-Request": "true", "HX-Request-URL": page_url},
    )
    assert response.status_code == 404


@pytest.fixture
def cote_dorien_dsil_simulation_projet(cote_d_or_perimetre):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__perimetre=cote_d_or_perimetre,
        assiette=1_000,
        dotation=DOTATION_DSIL,
    )
    simulation = SimulationFactory(
        enveloppe=DsilEnveloppeFactory(perimetre=cote_d_or_perimetre)
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
    )


@pytest.mark.parametrize("route, kwargs, data", PATCH_ROUTES_AND_DATA)
@pytest.mark.django_db
def test_regional_user_can_patch_projet_if_simulation_projet_is_associated_to_dsil_enveloppe_and_in_its_perimetre(
    client_with_bourguignon_user_logged,
    cote_dorien_dsil_simulation_projet,
    route,
    kwargs,
    data,
):
    page_url = reverse(
        "simulation:simulation-detail",
        kwargs={"slug": cote_dorien_dsil_simulation_projet.simulation.slug},
    )
    url = reverse(
        route,
        kwargs={"pk": cote_dorien_dsil_simulation_projet.pk, **kwargs},
    )
    with mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation",
    ):
        response = client_with_bourguignon_user_logged.post(
            url,
            data,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
        )
    assert response.status_code == 200


@pytest.fixture
def client_with_staff_user_logged():
    staff_user = CollegueFactory(is_staff=True)
    return ClientWithLoggedUserFactory(staff_user)


@pytest.mark.parametrize("route, kwargs, data", PATCH_ROUTES_AND_DATA)
@pytest.mark.django_db
def test_patch_projet_allowed_for_staff_user(
    client_with_staff_user_logged, cote_dorien_simulation_projet, route, kwargs, data
):
    page_url = reverse(
        "simulation:simulation-detail",
        kwargs={"slug": cote_dorien_simulation_projet.simulation.slug},
    )
    url = reverse(
        route,
        kwargs={"pk": cote_dorien_simulation_projet.pk, **kwargs},
    )
    response = client_with_staff_user_logged.post(
        url,
        data,
        headers={"HX-Request": "true", "HX-Request-URL": page_url},
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_edit_montant_post_returns_partial_regardless_of_referer(
    cote_d_or_perimetre, cote_dorien_simulation_projet
):
    """New CBVs always return the partial template on POST, no redirect."""
    client = get_client_with_referer(
        cote_d_or_perimetre,
        reverse(
            "simulation:simulation-detail",
            kwargs={"slug": cote_dorien_simulation_projet.simulation.slug},
        ),
    )

    url = reverse(
        "gsl_simulation:edit-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client.post(url, {"montant": "100"})
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"

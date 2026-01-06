from decimal import Decimal
from typing import cast
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages import INFO, SUCCESS, get_messages
from django.test.html import parse_html
from django.urls import reverse

from gsl_core.templatetags.gsl_filters import percent
from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.tests.factories import (
    FieldMappingForComputerFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import (
    DotationProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def ds_field():
    return FieldMappingForComputerFactory(ds_field_id=101112)


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return cast(
        SimulationProjet,
        SimulationProjetFactory(
            dotation_projet=dotation_projet,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=1000,
            simulation=simulation,
        ),
    )


@mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
def test_patch_status_simulation_projet_with_accepted_value_with_htmx(
    _mock_save_one_dossier_from_ds, client_with_user_logged, simulation_projet
):
    page_url = reverse(
        "simulation:simulation-detail", args=[simulation_projet.simulation.slug]
    )
    url = reverse(
        "simulation:simulation-projet-update-programmed-status",
        args=[simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
    )
    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    ) as mock_update_ds_annotations_for_one_dotation:
        mock_update_ds_annotations_for_one_dotation.return_value = None
        response = client_with_user_logged.post(
            url,
            follow=True,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
        )

    updated_simulation_projet = SimulationProjet.objects.get(id=simulation_projet.id)
    dotation_projet = DotationProjet.objects.get(
        id=updated_simulation_projet.dotation_projet.id
    )

    assert response.status_code == 200
    assert updated_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED
    assert "1 projet validé" in parse_html(response.content.decode())
    assert "0 projet refusé" in parse_html(response.content.decode())
    assert "0 projet notifié" in parse_html(response.content.decode())
    assert 'id="total-amount-granted">1\xa0000\xa0€</span>' in response.content.decode()


data_test = (
    (
        SimulationProjet.STATUS_ACCEPTED,
        "Le financement de ce projet vient d’être accepté avec la dotation DETR pour 1\xa0000,00\xa0€.",
        "accepted",
    ),
    (
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        "Le projet est accepté provisoirement dans cette simulation.",
        "provisionally_accepted",
    ),
    (
        SimulationProjet.STATUS_PROCESSING,
        "Le projet est revenu en traitement.",
        "draft",
    ),
)


@mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize("status, expected_message, expected_tag", data_test)
def test_patch_status_simulation_projet_gives_message(
    mock_ds_update,
    _mock_save_one_dossier_from_ds,
    client_with_user_logged,
    simulation_projet,
    status,
    expected_message,
    expected_tag,
):
    if status == SimulationProjet.STATUS_PROCESSING:
        simulation_projet.status = SimulationProjet.STATUS_ACCEPTED
        simulation_projet.dotation_projet.status = PROJET_STATUS_ACCEPTED
        simulation_projet.dotation_projet.save()
        simulation_projet.save()

    page_url = reverse(
        "simulation:simulation-projet-detail", args=[simulation_projet.id]
    )
    url = reverse(
        (
            "simulation:simulation-projet-update-simulation-status"
            if status in SimulationProjet.SIMULATION_PENDING_STATUSES
            else "simulation:simulation-projet-update-programmed-status"
        ),
        args=[simulation_projet.id, status],
    )
    response = client_with_user_logged.post(
        url, headers={"HX-Request": "true", "HX-Request-URL": page_url}, follow=True
    )

    if status == SimulationProjet.STATUS_ACCEPTED:
        mock_ds_update.assert_called_once_with(
            dossier=simulation_projet.projet.dossier_ds,
            user=client_with_user_logged.user,
            annotations_dotation_to_update=simulation_projet.dotation,
            dotations_to_be_checked=[simulation_projet.dotation],
            assiette=simulation_projet.dotation_projet.assiette,
            montant=Decimal(simulation_projet.montant),
            taux=Decimal(simulation_projet.taux),
        )

    assert response.status_code == 200

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1

    message = list(messages)[0]
    assert (
        message.level == INFO
        if status in SimulationProjet.SIMULATION_PENDING_STATUSES
        else SUCCESS
    )
    assert message.message == expected_message
    assert message.extra_tags == expected_tag


@pytest.mark.parametrize("data", ({"status": "invalid_status"}, {}))
def test_patch_status_simulation_projet_invalid_status(
    client_with_user_logged, simulation_projet, data
):
    url = reverse(
        "simulation:simulation-projet-update-simulation-status",
        args=[simulation_projet.id, "invalid"],
    )
    response = client_with_user_logged.post(
        url,
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(id=simulation_projet.id)
    assert response.status_code == 404
    assert updated_simulation_projet.status == SimulationProjet.STATUS_PROCESSING


@pytest.fixture
def accepted_simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__perimetre=collegue.perimetre,
        projet__is_budget_vert=False,
        dotation=DOTATION_DETR,
    )

    return cast(
        SimulationProjet,
        SimulationProjetFactory(
            dotation_projet=dotation_projet,
            status=SimulationProjet.STATUS_ACCEPTED,
            montant=1_000,
            simulation=simulation,
        ),
    )


@mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
def test_patch_status_simulation_projet_cancelling_all_when_error_in_ds_update(
    _mock_save_one_dossier_from_ds, client_with_user_logged, simulation_projet
):
    page_url = reverse(
        "simulation:simulation-projet-detail", args=[simulation_projet.id]
    )
    url = reverse(
        "simulation:simulation-projet-update-programmed-status",
        args=[simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
    )

    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation",
        side_effect=DsServiceException("Erreur !"),
    ):
        response = client_with_user_logged.post(
            url,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
            follow=True,
        )
    assert response.status_code == 200
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert "Erreur !" == message.message
    simulation_projet.refresh_from_db()
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING  # Not updated
    assert (
        simulation_projet.dotation_projet.status == PROJET_STATUS_PROCESSING
    )  # Not updated


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_patch_taux_simulation_projet(
    mock_ds_update,
    client_with_user_logged,
    accepted_simulation_projet,
):
    url = reverse(
        "simulation:patch-simulation-projet-taux", args=[accepted_simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"taux": "75.0"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(
        id=accepted_simulation_projet.id
    )

    mock_ds_update.assert_called_once_with(
        dossier=accepted_simulation_projet.projet.dossier_ds,
        user=client_with_user_logged.user,
        annotations_dotation_to_update=accepted_simulation_projet.dotation,
        dotations_to_be_checked=[accepted_simulation_projet.dotation],
        assiette=accepted_simulation_projet.dotation_projet.assiette,
        montant=7_500,
        taux=75.0,
    )
    assert response.status_code == 200
    assert updated_simulation_projet.taux == 75.0
    assert updated_simulation_projet.montant == 7_500
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">7\xa0500\xa0€</span>'
        in response.content.decode()
    )


@pytest.mark.parametrize("taux", ("-3", "100.1"))
def test_patch_taux_simulation_projet_with_wrong_value(
    client_with_user_logged, accepted_simulation_projet, taux, caplog
):
    url = reverse(
        "simulation:patch-simulation-projet-taux", args=[accepted_simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"taux": f"{taux}"},
        follow=True,
    )

    assert response.status_code == 200
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        f"Une erreur est survenue lors de la mise à jour du taux. Le taux {percent(float(taux))} doit être entre 0% and 100%"
        == message.message
    )

    accepted_simulation_projet.refresh_from_db()

    assert accepted_simulation_projet.taux == 10
    assert accepted_simulation_projet.montant == 1_000


def test_patch_taux_simulation_projet_cancelling_all_when_error_in_ds_update(
    client_with_user_logged, accepted_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux", args=[accepted_simulation_projet.id]
    )

    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation",
        side_effect=DsServiceException("Erreur !"),
    ):
        response = client_with_user_logged.post(
            url,
            {"taux": 75},
            follow=True,
        )
    assert response.status_code == 200
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        "Une erreur est survenue lors de la mise à jour du taux. Erreur !"
        == message.message
    )

    accepted_simulation_projet.refresh_from_db()
    assert accepted_simulation_projet.taux == 10.0  # Not updated
    assert accepted_simulation_projet.montant == 1_000  # Not updated


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_patch_montant_simulation_projet(
    mock_ds_update,
    client_with_user_logged,
    accepted_simulation_projet,
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        {"montant": "1267,32"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(
        id=accepted_simulation_projet.id
    )

    mock_ds_update.assert_called_once_with(
        dossier=accepted_simulation_projet.projet.dossier_ds,
        user=client_with_user_logged.user,
        annotations_dotation_to_update=accepted_simulation_projet.dotation,
        dotations_to_be_checked=[accepted_simulation_projet.dotation],
        assiette=accepted_simulation_projet.dotation_projet.assiette,
        montant=1267.32,
        taux=12.673,
    )

    assert response.status_code == 200
    assert updated_simulation_projet.montant == Decimal("1267.32")
    assert updated_simulation_projet.taux == Decimal("12.673")
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">1\xa0267\xa0€</span>'
        in response.content.decode()
    )


def test_patch_montant_simulation_projet_with_wrong_value(
    client_with_user_logged, accepted_simulation_projet, caplog
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        {"montant": 12_000},
        follow=True,
    )
    assert response.status_code == 200
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        "Une erreur est survenue lors de la mise à jour du montant. Le montant 12 000 € doit être supérieur ou égal à 0 € et inférieur ou égal à l'assiette (10 000 €)."
        == message.message
    )

    accepted_simulation_projet.refresh_from_db()
    assert accepted_simulation_projet.montant == 1_000
    assert accepted_simulation_projet.taux == 10.0


def test_patch_montant_simulation_projet_cancelling_all_when_error_in_ds_update(
    client_with_user_logged, accepted_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        args=[accepted_simulation_projet.id],
    )

    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation",
        side_effect=DsServiceException("Erreur !"),
    ):
        response = client_with_user_logged.post(
            url,
            {"montant": 2_000},
            follow=True,
        )
    assert response.status_code == 200
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        "Une erreur est survenue lors de la mise à jour du montant. Erreur !"
        == message.message
    )

    accepted_simulation_projet.refresh_from_db()
    assert accepted_simulation_projet.montant == 1_000
    assert accepted_simulation_projet.taux == 10.0


@pytest.mark.parametrize(
    "value, expected_value", (("True", True), ("False", False), ("", None))
)
def test_patch_detr_avis_commission_simulation_projet(
    client_with_user_logged, accepted_simulation_projet, value, expected_value
):
    url = reverse(
        "simulation:patch-dotation-projet",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        {"detr_avis_commission": value},
        follow=True,
    )

    updated_simulation_projet = SimulationProjet.objects.get(
        id=accepted_simulation_projet.id
    )

    assert response.status_code == 200
    assert (
        updated_simulation_projet.dotation_projet.detr_avis_commission is expected_value
    )


def test_patch_simulation_projet(
    client_with_user_logged,
    accepted_simulation_projet,
    ds_field,
):
    accepted_simulation_projet.dotation_projet.assiette = 1_000
    accepted_simulation_projet.montant = 500
    accepted_simulation_projet.save()
    accepted_simulation_projet.dotation_projet.save()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
    }

    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch("requests.post", return_value=mock_resp),
    ):
        url = reverse(
            "simulation:simulation-projet-detail",
            args=[accepted_simulation_projet.id],
        )
        response = client_with_user_logged.post(
            url,
            {"assiette": 2000, "montant": 500},
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 25
    assert "Les modifications ont été enregistrées avec succ\xe8s." in message.message

    accepted_simulation_projet.dotation_projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.dotation_projet.assiette == 2_000


def test_patch_simulation_projet_with_invalid_form(
    client_with_user_logged,
    accepted_simulation_projet,
):
    accepted_simulation_projet.dotation_projet.assiette = 1_000
    accepted_simulation_projet.montant = 500
    accepted_simulation_projet.save()
    accepted_simulation_projet.dotation_projet.save()

    url = reverse(
        "simulation:simulation-projet-detail",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        {"assiette": 200, "montant": 500},
        follow=True,
    )

    assert response.context["simulation_projet_form"].errors == {
        "montant": [
            "Le montant de la simulation ne peut pas être supérieur à l'assiette du projet."
        ]
    }
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        "Une erreur s'est produite lors de la soumission du formulaire."
        in message.message
    )

    accepted_simulation_projet.dotation_projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.dotation_projet.assiette == 1_000
    assert response.templates[0].name == "gsl_simulation/simulation_projet_detail.html"


possible_responses = [
    # Instructeur has no rights
    (
        {
            "data": {
                "dossierModifierAnnotations": {
                    "errors": [
                        {
                            "message": "L’instructeur n’a pas les droits d’accès à ce dossier"
                        }
                    ]
                }
            }
        },
        "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. Vous n'avez pas les droits suffisants pour modifier ce dossier.",
    ),
    # Invalid payload (ex: wrong dossier id)
    (
        {
            "errors": [
                {
                    "message": "dossierModifierAnnotationsPayload not found",
                }
            ],
            "data": {"dossierModifierAnnotations": None},
        },
        "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. dossierModifierAnnotationsPayload not found",
    ),
    # Invalid field id
    (
        {
            "errors": [
                {
                    "message": 'Invalid input: "field_NUL"',
                }
            ],
            "data": {"dossierModifierAnnotations": None},
        },
        'Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. Invalid input: "field_NUL"',
    ),
    # Invalid value
    (
        {
            "errors": [
                {
                    "message": 'Variable $input of type dossierModifierAnnotationsInput! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)',
                }
            ],
        },
        "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. ",
    ),
    # Other error
    (
        {
            "data": {
                "dossierModifierAnnotations": {"errors": [{"message": "Une erreur"}]}
            }
        },
        "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. Une erreur",
    ),
]


@pytest.mark.parametrize("response, error_msg", possible_responses)
def test_patch_simulation_projet_with_ds_error(
    client_with_user_logged, accepted_simulation_projet, ds_field, response, error_msg
):
    accepted_simulation_projet.dotation_projet.status = PROJET_STATUS_ACCEPTED
    accepted_simulation_projet.dotation_projet.assiette = 1_000
    accepted_simulation_projet.montant = 500
    accepted_simulation_projet.save()
    accepted_simulation_projet.dotation_projet.save()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response

    with (
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_ds_field_id",
            return_value=ds_field.ds_field_id,
        ),
        patch("requests.post", return_value=mock_resp),
    ):
        url = reverse(
            "simulation:simulation-projet-detail",
            args=[accepted_simulation_projet.id],
        )
        response = client_with_user_logged.post(
            url,
            {"assiette": 2000, "montant": 500, "taux": 25},
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert error_msg == message.message

    accepted_simulation_projet.dotation_projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.dotation_projet.assiette == 1_000


def test_patch_simulation_projet_with_ds_token_error(
    client_with_user_logged, accepted_simulation_projet, ds_field
):
    accepted_simulation_projet.dotation_projet.status = PROJET_STATUS_ACCEPTED
    accepted_simulation_projet.dotation_projet.assiette = 1_000
    accepted_simulation_projet.montant = 500
    accepted_simulation_projet.save()
    accepted_simulation_projet.dotation_projet.save()

    mock_resp = MagicMock()
    mock_resp.status_code = 403

    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch("requests.post", return_value=mock_resp),
    ):
        url = reverse(
            "simulation:simulation-projet-detail",
            args=[accepted_simulation_projet.id],
        )
        response = client_with_user_logged.post(
            url,
            {"assiette": 2000, "montant": 500},
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. Nous n'arrivons pas à nous connecter à Démarche Numérique."
        == message.message
    )

    accepted_simulation_projet.dotation_projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.dotation_projet.assiette == 1_000

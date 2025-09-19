import logging
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
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
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
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
    return CollegueFactory(perimetre=perimetre_departemental, ds_id="XXX")


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
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


def test_patch_status_simulation_projet_with_accepted_value_with_htmx(
    client_with_user_logged, simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": f"{SimulationProjet.STATUS_ACCEPTED}"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(id=simulation_projet.id)
    dotation_projet = DotationProjet.objects.get(
        id=updated_simulation_projet.dotation_projet.id
    )

    assert response.status_code == 200
    assert updated_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED
    assert "1 projet validé" in response.content.decode()
    assert "0 projet refusé" in response.content.decode()
    assert "0 projet notifié" in response.content.decode()
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">1\xa0000\xa0€</span>'
        in response.content.decode()
    )


def test_patch_status_simulation_projet_with_refused_value_with_htmx(
    client_with_user_logged, simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": f"{SimulationProjet.STATUS_REFUSED}"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    simulation_projet.refresh_from_db()
    dotation_projet = DotationProjet.objects.get(
        id=simulation_projet.dotation_projet.id
    )

    assert response.status_code == 200
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
    assert dotation_projet.status == PROJET_STATUS_REFUSED
    assert "0 projet validé" in response.content.decode()
    assert "1 projet refusé" in response.content.decode()
    assert "0 projet notifié" in response.content.decode()
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">0\xa0€</span>'
        in response.content.decode()
    )


data_test = (
    (
        SimulationProjet.STATUS_ACCEPTED,
        "Le financement de ce projet vient d’être accepté avec la dotation DETR pour 1\xa0000,00\xa0€.",
        "valid",
    ),
    (
        SimulationProjet.STATUS_REFUSED,
        "Le financement de ce projet vient d’être refusé.",
        "cancelled",
    ),
    (
        SimulationProjet.STATUS_DISMISSED,
        "Le projet est classé sans suite.",
        "dismissed",
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


@pytest.mark.parametrize("status, expected_message, expected_tag", data_test)
def test_patch_status_simulation_projet_with_refused_value_giving_message(
    client_with_user_logged, simulation_projet, status, expected_message, expected_tag
):
    if status == SimulationProjet.STATUS_PROCESSING:
        simulation_projet.status = SimulationProjet.STATUS_ACCEPTED
        simulation_projet.dotation_projet.status = PROJET_STATUS_ACCEPTED
        simulation_projet.dotation_projet.save()
        simulation_projet.save()

    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": status},
        follow=True,
    )

    assert response.status_code == 200

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1

    message = list(messages)[0]
    assert message.level == 20
    assert message.message == expected_message
    assert message.extra_tags == expected_tag


@pytest.mark.parametrize("data", ({"status": "invalid_status"}, {}))
def test_patch_status_simulation_projet_invalid_status(
    client_with_user_logged, simulation_projet, data
):
    url = reverse(
        "simulation:patch-simulation-projet-status", args=[simulation_projet.id]
    )
    response = client_with_user_logged.post(
        url,
        {"status": "invalid"},
        follow=True,
        headers={"HX-Request": "true"},
    )

    updated_simulation_projet = SimulationProjet.objects.get(id=simulation_projet.id)
    assert response.status_code == 500
    assert updated_simulation_projet.status == SimulationProjet.STATUS_PROCESSING


@pytest.fixture
def accepted_simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__perimetre=collegue.perimetre,
        projet__is_budget_vert=None,
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


def test_patch_taux_simulation_projet(
    client_with_user_logged, accepted_simulation_projet
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

    with caplog.at_level(logging.ERROR):
        accepted_simulation_projet.refresh_from_db()

    assert response.status_code == 500
    assert response.content == b'{"error": "An internal error has occurred."}'
    assert "must be between 0 and 100" in caplog.text
    assert accepted_simulation_projet.taux == 10
    assert accepted_simulation_projet.montant == 1_000


def test_patch_montant_simulation_projet(
    client_with_user_logged, accepted_simulation_projet
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

    assert response.status_code == 200
    assert updated_simulation_projet.montant == Decimal("1267.32")
    assert updated_simulation_projet.taux == Decimal("12.673")
    assert (
        '<span hx-swap-oob="innerHTML" id="total-amount-granted">1\xa0267\xa0€</span>'
        in response.content.decode()
    )


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


def test_two_fields_update_and_only_one_error(
    perimetre_departemental, accepted_simulation_projet
):
    collegue = CollegueFactory(perimetre=perimetre_departemental, ds_id="")
    client = ClientWithLoggedUserFactory(collegue)
    accepted_simulation_projet.projet.is_in_qpv = False
    accepted_simulation_projet.projet.is_attached_to_a_crte = False
    accepted_simulation_projet.projet.save()
    data = {
        "is_in_qpv": "on",
        "is_attached_to_a_crte": "on",
        "dotations": [DOTATION_DSIL],
    }

    with (
        patch(
            "gsl_demarches_simplifiees.services.DsService.update_ds_is_in_qpv",
            return_value=True,
        ),
        patch(
            "gsl_demarches_simplifiees.services.DsService.update_ds_is_attached_to_a_crte",
            side_effect=DsServiceException("Erreur !"),
        ),
    ):
        url = reverse(
            "simulation:patch-projet",
            args=[accepted_simulation_projet.id],
        )
        response = client.post(
            url,
            data,
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40  # Error
    assert (
        "Une erreur est survenue lors de la mise à jour de certaines informations sur Démarches Simplifiées (CRTE => Erreur !). Ces modifications n'ont pas été enregistrées."
        == message.message
    )

    accepted_simulation_projet.projet.refresh_from_db()

    assert response.status_code == 200

    assert (
        accepted_simulation_projet.projet.is_in_qpv is True
    )  # Only this field has been updated
    assert accepted_simulation_projet.projet.is_attached_to_a_crte is False


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
        "data": {"dossierModifierAnnotationDecimalNumber": {"clientMutationId": "test"}}
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
                "dossierModifierAnnotationDecimalNumber": {
                    "errors": [
                        {
                            "message": "L’instructeur n’a pas les droits d’accès à ce dossier"
                        }
                    ]
                }
            }
        },
        "Une erreur est survenue lors de la mise à jour des informations sur Démarches Simplifiées. Vous n'avez pas les droits suffisants pour modifier ce dossier.",
    ),
    # Invalid payload (ex: wrong dossier id)
    (
        {
            "errors": [
                {
                    "message": "dossierModifierAnnotationDecimalNumberPayload not found",
                }
            ],
            "data": {"dossierModifierAnnotationDecimalNumber": None},
        },
        "Une erreur est survenue lors de la mise à jour de certaines informations sur Démarches Simplifiées ({field}). Ces modifications n'ont pas été enregistrées.",
    ),
    # Invalid field id
    (
        {
            "errors": [
                {
                    "message": 'Invalid input: "field_NUL"',
                }
            ],
            "data": {"dossierModifierAnnotationDecimalNumber": None},
        },
        "Une erreur est survenue lors de la mise à jour de certaines informations sur Démarches Simplifiées ({field}). Ces modifications n'ont pas été enregistrées.",
    ),
    # Invalid value
    (
        {
            "errors": [
                {
                    "message": 'Variable $input of type dossierModifierAnnotationDecimalNumberInput! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)',
                }
            ]
        },
        "Une erreur est survenue lors de la mise à jour de certaines informations sur Démarches Simplifiées ({field}). Ces modifications n'ont pas été enregistrées.",
    ),
    # Other error
    (
        {
            "data": {
                "dossierModifierAnnotationDecimalNumber": {
                    "errors": [{"message": "Une erreur"}]
                }
            }
        },
        "Une erreur est survenue lors de la mise à jour de certaines informations sur Démarches Simplifiées ({field} => Une erreur). Ces modifications n'ont pas été enregistrées.",
    ),
]


@pytest.mark.parametrize("response, error_msg", possible_responses)
def test_patch_simulation_projet_with_ds_error(
    client_with_user_logged, accepted_simulation_projet, ds_field, response, error_msg
):
    accepted_simulation_projet.dotation_projet.assiette = 1_000
    accepted_simulation_projet.montant = 500
    accepted_simulation_projet.save()
    accepted_simulation_projet.dotation_projet.save()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response

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
    final_msg = error_msg.replace("{field}", "assiette")
    assert final_msg == message.message

    accepted_simulation_projet.dotation_projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.dotation_projet.assiette == 1_000


def test_patch_simulation_projet_with_ds_token_error(
    client_with_user_logged, accepted_simulation_projet, ds_field
):
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
        "Une erreur est survenue lors de la mise à jour des informations sur Démarches Simplifiées. Nous n'arrivons pas à nous connecter à Démarches Simplifiées."
        == message.message
    )

    accepted_simulation_projet.dotation_projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.dotation_projet.assiette == 1_000

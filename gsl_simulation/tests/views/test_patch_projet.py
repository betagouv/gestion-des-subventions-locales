from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.exceptions import InstructeurUnknown
from gsl_demarches_simplifiees.tests.factories import (
    FieldMappingFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_PROCESSING,
)
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
    return FieldMappingFactory(ds_field_id=101112)


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def user(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(user):
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def accepted_simulation_projet(user, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__dossier_ds__perimetre=user.perimetre,
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


@pytest.mark.parametrize(
    "field, data, expected_value",
    (
        ("is_budget_vert", {"is_budget_vert": "on"}, True),
        ("is_budget_vert", {}, False),
        ("is_attached_to_a_crte", {"is_attached_to_a_crte": "on"}, True),
        ("is_attached_to_a_crte", {}, False),
        ("is_in_qpv", {"is_in_qpv": "on"}, True),
        ("is_in_qpv", {}, False),
    ),
)
def test_patch_projet(
    client_with_user_logged,
    accepted_simulation_projet,
    field,
    data,
    expected_value,
    ds_field,
):
    accepted_simulation_projet.projet.__setattr__(field, not (expected_value))
    accepted_simulation_projet.projet.save()

    data["dotations"] = [DOTATION_DSIL]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "dossierModifierAnnotations": {
                "clientMutationId": "test",
            }
        }
    }

    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMapping.objects.get",
            return_value=ds_field,
        ),
        patch("requests.post", return_value=mock_resp),
    ):
        url = reverse(
            "simulation:patch-projet",
            args=[accepted_simulation_projet.id],
        )
        response = client_with_user_logged.post(
            url,
            data,
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 25
    assert "Les modifications ont été enregistrées avec succ\xe8s." in message.message

    accepted_simulation_projet.projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.projet.__getattribute__(field) is expected_value


def test_patch_projet_with_invalid_form(
    client_with_user_logged,
    accepted_simulation_projet,
):
    data = {"is_budget_vert": "WrongValue", "dotations": []}

    url = reverse(
        "simulation:patch-projet",
        args=[accepted_simulation_projet.id],
    )
    response = client_with_user_logged.post(
        url,
        data,
        follow=True,
    )
    assert "dotations" in response.context["projet_form"].errors

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        "Une erreur s'est produite lors de la soumission du formulaire."
        == message.message
    )
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_projet_detail.html"

    accepted_simulation_projet.projet.refresh_from_db()
    assert accepted_simulation_projet.projet.is_budget_vert is False  # Default value


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
        "Une erreur est survenue lors de la mise \xe0 jour des informations sur Démarche Numérique. Vous n'avez pas les droits suffisants pour modifier ce dossier.",
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
            ]
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


@pytest.mark.parametrize("mocked_response, msg", possible_responses)
def test_patch_projet_with_ds_service_exception_send_correct_error_msg_to_user_and_cancel_update(
    client_with_user_logged,
    accepted_simulation_projet,
    mocked_response,
    msg,
    ds_field,
):
    accepted_simulation_projet.projet.is_in_qpv = False
    accepted_simulation_projet.projet.save()

    data = {"is_in_qpv": "True", "dotations": [DOTATION_DSIL]}

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mocked_response

    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMapping.objects.get",
            return_value=ds_field,
        ),
        patch("requests.post", return_value=mock_resp),
    ):
        url = reverse(
            "simulation:patch-projet",
            args=[accepted_simulation_projet.id],
        )
        response = client_with_user_logged.post(
            url,
            data,
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40  # Error
    assert message.message == msg

    accepted_simulation_projet.projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.projet.is_in_qpv is False


def test_patch_projet_with_user_without_ds_profile(
    perimetre_departemental,
    accepted_simulation_projet,
    ds_field,
):
    user = CollegueFactory(perimetre=perimetre_departemental)
    client = ClientWithLoggedUserFactory(user)
    accepted_simulation_projet.projet.is_in_qpv = False
    accepted_simulation_projet.projet.save()

    data = {"is_in_qpv": "True", "dotations": [DOTATION_DSIL]}

    url = reverse(
        "simulation:patch-projet",
        args=[accepted_simulation_projet.id],
    )
    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMapping.objects.get",
            return_value=ds_field,
        ),
        patch(
            "gsl_demarches_simplifiees.services.DsService.update_checkboxes_annotations",
            side_effect=InstructeurUnknown(extra={"user_id": user.id}),
        ),
    ):
        resp = client.post(
            url,
            data,
            follow=True,
        )

    messages = get_messages(resp.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40  # Error
    assert (
        "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. Nous ne connaissons pas votre identifiant DN."
        == message.message
    )

    accepted_simulation_projet.projet.refresh_from_db()

    assert resp.status_code == 200
    assert accepted_simulation_projet.projet.is_in_qpv is False


def test_patch_projet_with_user_with_ds_connection_error(
    client_with_user_logged,
    accepted_simulation_projet,
    ds_field,
):
    accepted_simulation_projet.projet.is_in_qpv = False
    accepted_simulation_projet.projet.save()

    data = {"is_in_qpv": "True", "dotations": [DOTATION_DSIL]}

    mock_resp = MagicMock()
    mock_resp.status_code = 403

    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMapping.objects.get",
            return_value=ds_field,
        ),
        patch("requests.post", return_value=mock_resp),
    ):
        url = reverse(
            "simulation:patch-projet",
            args=[accepted_simulation_projet.id],
        )
        response = client_with_user_logged.post(
            url,
            data,
            follow=True,
        )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40  # Error
    assert (
        message.message
        == "Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. Nous n'arrivons pas à nous connecter à Démarche Numérique."
    )

    accepted_simulation_projet.projet.refresh_from_db()

    assert response.status_code == 200
    assert accepted_simulation_projet.projet.is_in_qpv is False

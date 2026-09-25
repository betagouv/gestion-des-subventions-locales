import copy
import json
import logging
from datetime import datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from gsl.core.tests.factories import CollegueFactory
from gsl.historique.models import ProjetAction
from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DS_TRAITEMENT_EVENT_ACCEPTE,
    DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
    DS_TRAITEMENT_EVENT_REFUSE,
)
from gsl.projet.tests.factories import ProjetFactory
from gsl_demarches_simplifiees.models import Dossier, FieldMapping
from gsl_demarches_simplifiees.services import (
    DsService,
    DsServiceException,
    FieldError,
    InstructeurUnknown,
    UserRightsError,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierDataFactory,
    DossierFactory,
    FieldMappingFactory,
    ProfileFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return CollegueFactory(ds_profile=ProfileFactory())


@pytest.fixture
def dossier():
    return DossierFactory(ds_id=456)


@pytest.fixture
def ds_field():
    return FieldMappingFactory(ds_field_id=101112)


def test_get_instructeur_id(caplog):
    caplog.set_level(logging.WARNING)
    user = CollegueFactory()
    service = DsService()

    with pytest.raises(InstructeurUnknown):
        service._get_instructeur_id(user)
    assert "User does not have DN id" in caplog.text


@pytest.mark.parametrize(
    "field, field_name",
    (
        ("annotations_is_qpv", "Projet situé en QPV"),
        ("annotations_is_crte", "Projet rattaché à un CRTE"),
        (
            "annotations_is_budget_vert",
            "Projet concourant à la transition écologique au sens budget vert",
        ),
        (
            "annotations_assiette_detr",
            "DETR - Montant des dépenses éligibles retenues (en euros)",
        ),
        (
            "annotations_montant_accorde_detr",
            "DETR - Montant définitif de la subvention (en euros)",
        ),
        (
            "annotations_taux_detr",
            "DETR - Taux de subvention (%)",
        ),
        ("field_unknown", "field_unknown"),
    ),
)
def test_get_ds_field_id(dossier: Dossier, field, field_name, caplog):
    caplog.set_level(logging.ERROR)
    ds_service = DsService()

    with patch(
        "gsl_demarches_simplifiees.services.FieldMapping.actives.get",
        side_effect=FieldMapping.DoesNotExist,
    ):
        with pytest.raises(FieldError) as exc_info:
            ds_service._get_ds_field_id(dossier, field)

    assert (
        str(exc_info.value)
        == f'Le champ "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche_number}.'
    )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "Field not found in demarche"
    assert getattr(record, "field_name") == field_name
    assert getattr(record, "demarche_ds_number") == dossier.ds_demarche_number
    assert getattr(record, "dossier_ds_number") == dossier.ds_number


@pytest.mark.parametrize(
    "mutation_type",
    ("dismiss", "annotations"),
)
def test_check_results_with_uncorrect_user_rights(dossier, user, mutation_type, caplog):
    caplog.set_level(logging.INFO)
    ds_service = DsService()
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]
    response = {
        "data": {
            mutation_data_name: {
                "errors": [
                    {"message": "L’instructeur n’a pas les droits d’accès à ce dossier"}
                ]
            }
        }
    }

    with pytest.raises(UserRightsError) as exc_info:
        ds_service._check_results(
            response,
            dossier,
            user,
            mutation_type,
        )

    assert (
        str(exc_info.value)
        == "Vous n'avez pas les droits suffisants pour modifier ce dossier."
    )
    assert "Instructeur has no rights on the dossier" in caplog.text


possible_responses = [
    # Invalid payload (ex: wrong dossier id)
    (
        {
            "errors": [{"message": "__MUTATION_KEY__Payload not found"}],
            "data": {"__MUTATION_KEY__": None},
        },
        "__MUTATION_KEY__Payload not found",
    ),
    # Invalid field id
    (
        {
            "errors": [{"message": 'Invalid input: "field_NUL"'}],
            "data": {"__MUTATION_KEY__": None},
        },
        'Invalid input: "field_NUL"',
    ),
    # Invalid value
    (
        {
            "errors": [
                {
                    "message": 'Variable $input of type __MUTATION_KEY__Input! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)'
                }
            ]
        },
        'Variable $input of type __MUTATION_KEY__Input! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)',
    ),
    # Other error
    (
        {"data": {"__MUTATION_KEY__": {"errors": [{"message": "Une erreur"}]}}},
        "Une erreur",
    ),
    # Invalid annotation type
    (
        {
            "data": {
                "__MUTATION_KEY__": {
                    "errors": [
                        {
                            "message": 'L‘annotation "Q2hhbXAtNTQ0MTQ4Mg==" n’est pas de type attendu'
                        }
                    ]
                }
            }
        },
        'L‘annotation "Q2hhbXAtNTQ0MTQ4Mg==" n’est pas de type attendu',
    ),
    # Si je me trompe dans le type de la valeur passée
    (
        {
            "errors": [
                {
                    "message": "Variable $input of type DossierModifierAnnotationsInput! was provided invalid value for annotations.3.value.checkbox (Could not coerce value 5000 to Boolean)"
                }
            ]
        },
        "Variable $input of type DossierModifierAnnotationsInput! was provided invalid value for annotations.3.value.checkbox (Could not coerce value 5000 to Boolean)",
    ),
    # Si je me trompe dans l'id d'une annotation passée
    (
        {"errors": [{"message": 'Invalid input: "Q2hhbXAtNTQ0MTQ4Mg="'}]},
        'Invalid input: "Q2hhbXAtNTQ0MTQ4Mg="',
    ),
    # id du dossier inconnu
    (
        {"errors": [{"message": "DossierModifierAnnotationsPayload not found"}]},
        "DossierModifierAnnotationsPayload not found",
    ),
    # instructeur inconnu
    (
        {
            "errors": [
                {"message": "L’instructeur n’a pas les droits d’accès à ce dossier"}
            ]
        },
        "L’instructeur n’a pas les droits d’accès à ce dossier",
    ),
    # Si je me trompe, ex: j'ai mis annotation au lieu de annotations
    (
        {
            "errors": [
                {
                    "message": "Variable $input of type DossierModifierAnnotationsInput! was provided invalid value for annotation (Field is not defined on DossierModifierAnnotationsInput), annotations (Expected value to not be null)"
                }
            ]
        },
        "Variable $input of type DossierModifierAnnotationsInput! was provided invalid value for annotation (Field is not defined on DossierModifierAnnotationsInput), annotations (Expected value to not be null)",
    ),
]


@pytest.mark.parametrize("mutation_type", ("dismiss", "annotations"))
@pytest.mark.parametrize("mocked_response, msg", possible_responses)
def test_check_results(
    user,
    dossier,
    mutation_type,
    mocked_response,
    msg,
    caplog,
):
    caplog.set_level(logging.WARNING)
    ds_service = DsService()

    value = True if mutation_type == "checkbox" else 1.5
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]

    # clone + replace __MUTATION_KEY__ dynamically
    response = copy.deepcopy(mocked_response)
    response_str = str(response).replace("__MUTATION_KEY__", mutation_data_name)
    response = eval(response_str)  # safe because we control data

    with pytest.raises(DsServiceException) as exc_info:
        ds_service._check_results(
            response,
            dossier,
            user,
            mutation_type,
            value=value,
        )

    final_msg = msg.replace("__MUTATION_KEY__", mutation_data_name)
    assert str(exc_info.value) == final_msg
    record = caplog.records[0]
    assert "Error in DN mutation" in record.message
    assert record.dossier_ds_number == dossier.ds_number
    assert record.user_id == user.id
    assert record.mutation_key == mutation_data_name
    assert record.field is None
    assert record.value == value
    assert record.error == [final_msg]


def test_dismiss_in_ds():
    dossier = DossierFactory()
    user = CollegueFactory()
    ds_service = DsService()
    with (
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_classer_sans_suite"
        ) as mock_dossier_classer_sans_suite,
        patch(
            "gsl_demarches_simplifiees.services.DsService._check_results"
        ) as mock_check_results,
        # DossierConverter (called by refresh_dossier_from_saved_data) needs a
        # full DN payload (champs/annotations/demarche, ...): irrelevant here.
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        results = {"results": {"data": {}}}
        mock_dossier_classer_sans_suite.return_value = results

        ds_service.dismiss_in_ds(dossier, user, motivation="motivation")

        mock_get_instructeur_id.assert_called_once_with(user)
        mock_dossier_classer_sans_suite.assert_called_once_with(
            dossier.ds_id, "instructeur_id", "motivation", document=None
        )
        mock_check_results.assert_called_once_with(
            results, dossier, user, "dismiss", value="motivation"
        )


@pytest.mark.parametrize(
    "method_name, mutator_method, mutation_key, expected_event",
    [
        (
            "accept_in_ds",
            "dossier_accepter",
            "dossierAccepter",
            DS_TRAITEMENT_EVENT_ACCEPTE,
        ),
        (
            "dismiss_in_ds",
            "dossier_classer_sans_suite",
            "dossierClasserSansSuite",
            DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
        ),
        (
            "refuser_in_ds",
            "dossier_refuser",
            "dossierRefuser",
            DS_TRAITEMENT_EVENT_REFUSE,
        ),
    ],
)
def test_in_ds_updates_ds_date_traitement(
    user, dossier, method_name, mutator_method, mutation_key, expected_event
):
    """accept_in_ds/dismiss_in_ds/refuser_in_ds should update
    dossier.ds_date_traitement from DN's own response (using the most recent
    dateTraitement in `dossier.traitements` — not necessarily the list's
    last entry)."""
    ds_service = DsService()
    expected_date_str = "2025-06-25T11:46:30+02:00"
    expected_date = datetime.fromisoformat(expected_date_str)

    mock_results = {
        "data": {
            mutation_key: {
                "dossier": {
                    "dateTraitement": expected_date_str,
                    "traitements": [
                        {
                            "id": "traitement-2",
                            "dateTraitement": "2025-06-25T11:46:30+02:00",
                            "event": expected_event,
                        },
                        {
                            "id": "traitement-1",
                            "dateTraitement": "2025-06-20T09:00:00+02:00",
                            "event": expected_event,
                        },
                    ],
                }
            }
        }
    }

    with (
        patch(
            f"gsl_demarches_simplifiees.ds_client.DsMutator.{mutator_method}"
        ) as mock_mutator_method,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        mock_mutator_method.return_value = mock_results

        dossier.ds_date_traitement = None
        dossier.save()

        getattr(ds_service, method_name)(
            dossier, user, document=None, motivation="motivation"
        )

        dossier.refresh_from_db()
        assert dossier.ds_date_traitement is not None
        assert (
            abs(
                (
                    dossier.ds_date_traitement
                    - expected_date.astimezone(dt_timezone.utc)
                ).total_seconds()
            )
            < 1
        )


def test_accept_in_ds_keeps_ds_date_traitement_when_dn_response_has_none(user, dossier):
    """A response missing dateTraitement (unexpected shape) must not crash and must
    not erase a previously known date."""
    ds_service = DsService()
    original_date = dossier.ds_date_traitement

    with (
        patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_accepter"
        ) as mock_dossier_accepter,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        mock_dossier_accepter.return_value = {"data": {"dossierAccepter": {}}}

        ds_service.accept_in_ds(dossier, user, document=None, motivation="motivation")

        dossier.refresh_from_db()
        assert dossier.ds_date_traitement == original_date


@pytest.mark.parametrize(
    "method_name, mutator_method, mutation_key",
    [
        ("accept_in_ds", "dossier_accepter", "dossierAccepter"),
        ("dismiss_in_ds", "dossier_classer_sans_suite", "dossierClasserSansSuite"),
        ("refuser_in_ds", "dossier_refuser", "dossierRefuser"),
    ],
)
def test_in_ds_merges_only_present_fields_into_dossier_data(
    user, dossier, method_name, mutator_method, mutation_key
):
    """The mutation response only carries a handful of fields (cf
    ds_mutations.gql): merging it into dossier.data.raw_data must not erase
    unrelated fields (champs, annotations, demandeur, ...) already stored
    there by a previous full sync."""
    DossierDataFactory(
        dossier=dossier,
        raw_data={
            "number": 123,
            "dateTraitement": "2022-06-25T11:46:30+02:00",
            "champs": [{"id": "champ-1"}],
        },
    )

    mock_results = {
        "data": {
            mutation_key: {
                "dossier": {
                    "state": "accepte",
                    "dateTraitement": "2025-06-25T11:46:30+02:00",
                    "traitements": [
                        {
                            "id": "traitement-1",
                            "dateTraitement": "2025-06-25T11:46:30+02:00",
                        }
                    ],
                }
            }
        }
    }

    with (
        patch(
            f"gsl_demarches_simplifiees.ds_client.DsMutator.{mutator_method}"
        ) as mock_mutator_method,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        mock_mutator_method.return_value = mock_results

        getattr(DsService(), method_name)(
            dossier, user, document=None, motivation="motivation"
        )

        dossier.refresh_from_db()
        raw_data = dossier.data.raw_data
        assert raw_data["number"] == 123
        assert raw_data["champs"] == [{"id": "champ-1"}]
        assert raw_data["state"] == "accepte"
        assert raw_data["dateTraitement"] == "2025-06-25T11:46:30+02:00"
        assert raw_data["traitements"] == [
            {"id": "traitement-1", "dateTraitement": "2025-06-25T11:46:30+02:00"}
        ]


@pytest.mark.parametrize(
    "method_name, mutator_method, mutation_key, expected_event",
    [
        (
            "accept_in_ds",
            "dossier_accepter",
            "dossierAccepter",
            DS_TRAITEMENT_EVENT_ACCEPTE,
        ),
        (
            "dismiss_in_ds",
            "dossier_classer_sans_suite",
            "dossierClasserSansSuite",
            DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
        ),
        (
            "refuser_in_ds",
            "dossier_refuser",
            "dossierRefuser",
            DS_TRAITEMENT_EVENT_REFUSE,
        ),
    ],
)
def test_in_ds_creates_notified_projet_action_with_turgot_source(
    user, dossier, method_name, mutator_method, mutation_key, expected_event
):
    """accept_in_ds/dismiss_in_ds/refuser_in_ds must create the ProjetAction
    (source Turgot) recording the notification: right action_type, actor,
    motivation, the Traitement DN's own date, its id as source_id, and the
    signed document attached."""
    projet = ProjetFactory(dossier_ds=dossier)
    document = SimpleUploadedFile("justificatif.pdf", b"%PDF-1.4 fake content")

    mock_results = {
        "data": {
            mutation_key: {
                "dossier": {
                    "dateTraitement": "2025-06-25T11:46:30+02:00",
                    "traitements": [
                        {
                            "id": "traitement-1",
                            "dateTraitement": "2025-06-25T11:46:30+02:00",
                            "event": expected_event,
                        }
                    ],
                }
            }
        }
    }

    with (
        patch(
            f"gsl_demarches_simplifiees.ds_client.DsMutator.{mutator_method}"
        ) as mock_mutator_method,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        mock_mutator_method.return_value = mock_results

        getattr(DsService(), method_name)(
            dossier, user, document=document, motivation="Motif de la décision"
        )

    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == ProjetAction.TYPE_NOTIFIED
    assert action.source == ProjetAction.SOURCE_TURGOT
    assert action.actor == user
    assert action.source_id == "traitement-1"
    assert action.details == "Motif de la décision"
    assert action.created_at == datetime.fromisoformat("2025-06-25T11:46:30+02:00")
    assert "justificatif" in action.document.name
    assert action.document.name.endswith(".pdf")


@pytest.mark.parametrize(
    "method_name, mutator_method, mutation_key",
    [
        ("accept_in_ds", "dossier_accepter", "dossierAccepter"),
        ("dismiss_in_ds", "dossier_classer_sans_suite", "dossierClasserSansSuite"),
        ("refuser_in_ds", "dossier_refuser", "dossierRefuser"),
    ],
)
def test_in_ds_creates_dossier_data_when_missing(
    user, dossier, method_name, mutator_method, mutation_key
):
    assert dossier.data is None

    mock_results = {"data": {mutation_key: {"dossier": {"state": "accepte"}}}}

    with (
        patch(
            f"gsl_demarches_simplifiees.ds_client.DsMutator.{mutator_method}"
        ) as mock_mutator_method,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        mock_mutator_method.return_value = mock_results

        getattr(DsService(), method_name)(
            dossier, user, document=None, motivation="motivation"
        )

        dossier.refresh_from_db()
        assert dossier.data is not None
        assert dossier.data.raw_data == {"state": "accepte"}


class TestCreateProjetActionForMutation:
    def test_creates_projet_action_with_turgot_source_and_given_action_type(
        self, user, dossier
    ):
        projet = ProjetFactory(dossier_ds=dossier)
        document = SimpleUploadedFile("justificatif.pdf", b"%PDF-1.4 fake content")
        dossier_data = {
            "traitements": [
                {
                    "id": "traitement-1",
                    "dateTraitement": "2025-06-25T11:46:30+02:00",
                    "event": "accepte",
                }
            ]
        }

        DsService()._create_projet_action_for_mutation(
            dossier,
            user,
            "accept",
            ProjetAction.TYPE_NOTIFIED,
            dossier_data,
            document=document,
            motivation="Motif de la décision",
        )

        action = ProjetAction.objects.get(projet=projet)
        assert action.action_type == ProjetAction.TYPE_NOTIFIED
        assert action.source == ProjetAction.SOURCE_TURGOT
        assert action.actor == user
        assert action.source_id == "traitement-1"
        assert action.details == "Motif de la décision"
        assert action.created_at == datetime.fromisoformat("2025-06-25T11:46:30+02:00")
        assert "justificatif" in action.document.name

    def test_falls_back_to_now_when_no_matching_traitement(self, user, dossier):
        projet = ProjetFactory(dossier_ds=dossier)

        before = timezone.now()
        DsService()._create_projet_action_for_mutation(
            dossier, user, "accept", ProjetAction.TYPE_NOTIFIED, {}
        )
        after = timezone.now()

        action = ProjetAction.objects.get(projet=projet)
        assert action.action_type == ProjetAction.TYPE_NOTIFIED
        assert action.source == ProjetAction.SOURCE_TURGOT
        assert action.actor == user
        assert action.source_id == ""
        assert before <= action.created_at <= after

    def test_does_nothing_when_dossier_has_no_projet(self, user, dossier):
        DsService()._create_projet_action_for_mutation(
            dossier, user, "accept", ProjetAction.TYPE_NOTIFIED, {}
        )

        assert not ProjetAction.objects.exists()


@pytest.mark.parametrize(
    "method_name, mutator_method, mutation_key",
    [
        (
            "passer_en_instruction",
            "dossier_passer_en_instruction",
            "dossierPasserEnInstruction",
        ),
        (
            "repasser_en_instruction",
            "dossier_repasser_en_instruction",
            "dossierRepasserEnInstruction",
        ),
    ],
)
def test_passer_repasser_en_instruction_calls_refresh_dossier_from_saved_data(
    user, dossier, method_name, mutator_method, mutation_key
):
    projet = ProjetFactory(dossier_ds=dossier)
    expected_event = DsService.MUTATION_EXPECTED_EVENTS[method_name]
    mock_results = {
        "data": {
            mutation_key: {
                "dossier": {
                    "dateDerniereModification": "x",
                    "traitements": [
                        {
                            "id": "traitement-1",
                            "dateTraitement": "2024-01-15T10:30:00+01:00",
                            "event": expected_event,
                        }
                    ],
                }
            }
        }
    }

    with (
        patch(
            f"gsl_demarches_simplifiees.ds_client.DsMutator.{mutator_method}"
        ) as mock_mutator_method,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ) as mock_refresh,
    ):
        mock_mutator_method.return_value = mock_results

        getattr(DsService(), method_name)(dossier, user)

        mock_refresh.assert_called_once_with(dossier)

    projet.refresh_from_db()
    assert projet.notified_at is None

    action_types = {
        "passer_en_instruction": ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        "repasser_en_instruction": ProjetAction.TYPE_RETOUR_EN_INSTRUCTION,
    }
    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == action_types[method_name]
    assert action.source == ProjetAction.SOURCE_TURGOT
    assert action.actor == user
    assert action.source_id == "traitement-1"
    assert action.created_at == datetime.fromisoformat("2024-01-15T10:30:00+01:00")


@pytest.mark.parametrize(
    "method_name, mutator_method, mutation_key",
    [
        (
            "passer_en_instruction",
            "dossier_passer_en_instruction",
            "dossierPasserEnInstruction",
        ),
        (
            "repasser_en_instruction",
            "dossier_repasser_en_instruction",
            "dossierRepasserEnInstruction",
        ),
    ],
)
def test_passer_repasser_en_instruction_merges_only_present_fields_into_dossier_data(
    user, dossier, method_name, mutator_method, mutation_key
):
    DossierDataFactory(
        dossier=dossier, raw_data={"number": 123, "champs": [{"id": "champ-1"}]}
    )
    projet = ProjetFactory(dossier_ds=dossier)
    expected_event = DsService.MUTATION_EXPECTED_EVENTS[method_name]
    mock_results = {
        "data": {
            mutation_key: {
                "dossier": {
                    "dateDerniereModification": "2024-01-15T10:30:00+01:00",
                    "state": "en_instruction",
                    "traitements": [
                        {
                            "id": "traitement-1",
                            "dateTraitement": "2024-01-15T10:30:00+01:00",
                            "event": expected_event,
                        }
                    ],
                }
            }
        }
    }

    with (
        patch(
            f"gsl_demarches_simplifiees.ds_client.DsMutator.{mutator_method}"
        ) as mock_mutator_method,
        patch("gsl_demarches_simplifiees.services.DsService._check_results"),
        patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ),
    ):
        mock_mutator_method.return_value = mock_results

        getattr(DsService(), method_name)(dossier, user)

        dossier.refresh_from_db()
        raw_data = dossier.data.raw_data
        assert raw_data["number"] == 123
        assert raw_data["champs"] == [{"id": "champ-1"}]
        assert raw_data["state"] == "en_instruction"
        assert raw_data["traitements"] == [
            {
                "id": "traitement-1",
                "dateTraitement": "2024-01-15T10:30:00+01:00",
                "event": expected_event,
            }
        ]

    # refresh_dossier_from_saved_data is mocked out above, so nothing here
    # sets notified_at: it stays null, as it was at creation.
    projet.refresh_from_db()
    assert projet.notified_at is None

    action_types = {
        "passer_en_instruction": ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        "repasser_en_instruction": ProjetAction.TYPE_RETOUR_EN_INSTRUCTION,
    }
    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == action_types[method_name]
    assert action.source == ProjetAction.SOURCE_TURGOT
    assert action.actor == user
    assert action.source_id == "traitement-1"
    assert action.created_at == datetime.fromisoformat("2024-01-15T10:30:00+01:00")


def test_passer_en_instruction_updates_dossier_state_and_traitements_end_to_end(
    user, dossier
):
    with open(Path(__file__).parent / "ds_fixtures" / "dossier_data.json") as handle:
        full_raw_data = json.loads(handle.read())
    assert full_raw_data["state"] == "en_construction"
    original_champs_count = len(full_raw_data["champs"])

    DossierDataFactory(dossier=dossier, raw_data=full_raw_data)
    dossier.ds_state = Dossier.STATE_EN_CONSTRUCTION
    dossier.porteur_de_projet_arrondissement = dossier.perimetre.arrondissement
    dossier.save()
    projet = ProjetFactory(dossier_ds=dossier)

    new_traitements = [
        {
            "id": "traitement-1",
            "dateTraitement": "2024-01-15T10:30:00+01:00",
            "event": "passe_en_instruction",
        }
    ]
    mock_results = {
        "data": {
            "dossierPasserEnInstruction": {
                "dossier": {
                    "dateDerniereModification": "2024-01-15T10:30:00+01:00",
                    "state": "en_instruction",
                    "traitements": new_traitements,
                }
            }
        }
    }

    with (
        patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_passer_en_instruction",
            return_value=mock_results,
        ) as mock_dossier_passer_en_instruction,
        patch(
            "gsl_demarches_simplifiees.services.DsService._check_results"
        ) as mock_check_results,
    ):
        DsService().passer_en_instruction(dossier, user)

        # Verify the mutator was called with correct parameters
        mock_dossier_passer_en_instruction.assert_called_once_with(
            dossier.ds_id, user.ds_id
        )

        # Verify _check_results was called
        mock_check_results.assert_called_once_with(
            mock_results, dossier, user, "passer_en_instruction"
        )

    # Verify dossier state was updated
    dossier.refresh_from_db()
    assert dossier.ds_state == Dossier.STATE_EN_INSTRUCTION
    assert dossier.data.raw_data["traitements"] == new_traitements
    assert len(dossier.data.raw_data["champs"]) == original_champs_count

    # Verify date was updated (Django converts ISO string to datetime)
    assert dossier.ds_date_derniere_modification is not None
    assert isinstance(dossier.ds_date_derniere_modification, datetime)

    # A dossier back in instruction is not treated: notified_at is cleared.
    projet.refresh_from_db()
    assert projet.notified_at is None

    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION
    assert action.source == ProjetAction.SOURCE_TURGOT
    assert action.actor == user
    assert action.source_id == "traitement-1"
    assert action.created_at == datetime.fromisoformat("2024-01-15T10:30:00+01:00")


def test_update_ds_annotations_for_one_dotation_annotations_dict(user, dossier):
    """Test that update_ds_annotations_for_one_dotation builds annotations dict correctly"""
    ds_service = DsService()

    # Mock field IDs
    field_ids = {
        "annotations_dotation": "field_dotations_123",
        "annotations_assiette_dsil": "field_assiette_dsil_456",
        "annotations_assiette_detr": "field_assiette_detr_789",
        "annotations_montant_accorde_dsil": "field_montant_dsil_101",
        "annotations_montant_accorde_detr": "field_montant_detr_102",
        "annotations_taux_dsil": "field_taux_dsil_103",
        "annotations_taux_detr": "field_taux_detr_104",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results") as mock_check_results,
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        # Test with DSIL, all parameters provided
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            dotations_to_be_checked=[DOTATION_DSIL, DOTATION_DETR],
            annotations_dotation_to_update=DOTATION_DSIL,
            assiette=1000.50,
            montant=500.25,
            taux=50.0,
        )

        # Verify annotations dict was built correctly
        call_args = mock_mutator.dossier_modifier_annotations.call_args
        annotations = call_args[0][2]  # Third argument is annotations

        assert len(annotations) == 4  # dotations + assiette + montant + taux

        # Check dotations annotation (always first)
        assert annotations[0] == {
            "id": "field_dotations_123",
            "value": {"multipleDropDownList": [DOTATION_DSIL, DOTATION_DETR]},
        }

        # Check assiette annotation
        assert annotations[1] == {
            "id": "field_assiette_dsil_456",
            "value": {"decimalNumber": 1000.50},
        }

        # Check montant annotation
        assert annotations[2] == {
            "id": "field_montant_dsil_101",
            "value": {"decimalNumber": 500.25},
        }

        # Check taux annotation
        assert annotations[3] == {
            "id": "field_taux_dsil_103",
            "value": {"decimalNumber": 50.0},
        }

        # Verify _check_results was called with annotations
        mock_check_results.assert_called_once()
        check_call_args = mock_check_results.call_args[0]
        assert check_call_args[3] == "annotations"  # mutation_type
        assert mock_check_results.call_args[1] == {"value": annotations}


@pytest.mark.parametrize(
    "dotation, expected_suffix",
    [(DOTATION_DSIL, "dsil"), (DOTATION_DETR, "detr")],
)
def test_update_ds_annotations_for_one_dotation_suffix(
    user, dossier, dotation, expected_suffix
):
    """Test that correct suffix is used based on dotation type"""
    ds_service = DsService()

    field_ids = {
        "annotations_dotation": "field_dotations_123",
        f"annotations_assiette_{expected_suffix}": f"field_assiette_{expected_suffix}_456",
        f"annotations_montant_accorde_{expected_suffix}": f"field_montant_{expected_suffix}_101",
        f"annotations_taux_{expected_suffix}": f"field_taux_{expected_suffix}_103",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results"),
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            dotations_to_be_checked=[dotation],
            annotations_dotation_to_update=dotation,
            assiette=1000.0,
            montant=500.0,
            taux=50.0,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]

        # Verify suffix is used in field IDs
        assert annotations[1]["id"] == f"field_assiette_{expected_suffix}_456"
        assert annotations[2]["id"] == f"field_montant_{expected_suffix}_101"
        assert annotations[3]["id"] == f"field_taux_{expected_suffix}_103"


@pytest.mark.parametrize(
    "assiette, montant, taux, expected_count",
    [
        (None, None, None, 1),  # Only dotations
        (1000.0, None, None, 2),  # dotations + assiette
        (None, 500.0, None, 2),  # dotations + montant
        (None, None, 50.0, 2),  # dotations + taux
        (1000.0, 500.0, None, 3),  # dotations + assiette + montant
        (1000.0, None, 50.0, 3),  # dotations + assiette + taux
        (None, 500.0, 50.0, 3),  # dotations + montant + taux
        (1000.0, 500.0, 50.0, 4),  # All parameters
    ],
)
def test_update_ds_annotations_for_one_dotation_optional_params(
    user, dossier, assiette, montant, taux, expected_count
):
    """Test that optional parameters (assiette, montant, taux) are only included when not None"""
    ds_service = DsService()

    field_ids = {
        "annotations_dotation": "field_dotations_123",
        "annotations_assiette_detr": "field_assiette_detr_456",
        "annotations_montant_accorde_detr": "field_montant_detr_101",
        "annotations_taux_detr": "field_taux_detr_103",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results"),
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            dotations_to_be_checked=[DOTATION_DETR],
            annotations_dotation_to_update=DOTATION_DETR,
            assiette=assiette,
            montant=montant,
            taux=taux,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]

        # Verify correct number of annotations
        assert len(annotations) == expected_count

        # First annotation should always be dotations
        assert annotations[0]["id"] == "field_dotations_123"
        assert "multipleDropDownList" in annotations[0]["value"]

        # Verify only non-None parameters are included
        annotation_ids = [ann["id"] for ann in annotations[1:]]
        if assiette is not None:
            assert "field_assiette_detr_456" in annotation_ids
        if montant is not None:
            assert "field_montant_detr_101" in annotation_ids
        if taux is not None:
            assert "field_taux_detr_103" in annotation_ids


def test_update_ds_annotations_for_one_dotation_dotations_list(user, dossier):
    """Test that dotations_to_be_checked is correctly passed as multipleDropDownList"""
    ds_service = DsService()

    field_ids = {
        "annotations_dotation": "field_dotations_123",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results"),
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        dotations_list = [DOTATION_DSIL]
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            dotations_to_be_checked=dotations_list,
            annotations_dotation_to_update=DOTATION_DSIL,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]

        # Verify dotations list is correctly formatted
        assert annotations[0]["value"]["multipleDropDownList"] == dotations_list

        # Test with multiple dotations
        dotations_list = [DOTATION_DSIL, DOTATION_DETR]
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            dotations_to_be_checked=dotations_list,
            annotations_dotation_to_update=DOTATION_DSIL,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]
        assert annotations[0]["value"]["multipleDropDownList"] == dotations_list


class TestUpdateUpdatedAtFromMultipleAnnotations:
    def test_update_updated_at_from_multiple_annotations_with_user_data(self, dossier):
        """Test with the actual data structure provided by the user"""
        ds_service = DsService()

        results = {
            "data": {
                "dossierModifierAnnotations": {
                    "annotations": [
                        {
                            "id": "Q2hhbXAtNTQ0MTQ2NA==",
                            "updatedAt": "2025-12-08T11:26:17+01:00",
                        },
                        {
                            "id": "Q2hhbXAtNTQ0MjcxMg==",
                            "updatedAt": "2025-12-08T11:35:14+01:00",
                        },
                        {
                            "id": "Q2hhbXAtNTQ0MjcxMw==",
                            "updatedAt": "2025-12-08T11:35:14+01:00",
                        },
                        {
                            "id": "Q2hhbXAtNTQ0MjcxNA==",
                            "updatedAt": "2025-12-08T11:26:17+01:00",
                        },
                    ],
                    "errors": None,
                }
            }
        }

        dossier.ds_date_derniere_modification = None
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        expected_updated_at = datetime.fromisoformat("2025-12-08T11:35:14+01:00")
        assert dossier.ds_date_derniere_modification == expected_updated_at

    def test_update_updated_at_from_multiple_annotations_most_recent(self, dossier):
        """Test that it correctly identifies the most recent updatedAt"""
        ds_service = DsService()

        results = {
            "data": {
                "dossierModifierAnnotations": {
                    "annotations": [
                        {"id": "1", "updatedAt": "2025-01-01T10:00:00+01:00"},
                        {"id": "2", "updatedAt": "2025-01-01T12:00:00+01:00"},
                        {"id": "3", "updatedAt": "2025-01-01T11:00:00+01:00"},
                    ],
                    "errors": None,
                }
            }
        }

        dossier.ds_date_derniere_modification = None
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        expected_updated_at = datetime.fromisoformat("2025-01-01T12:00:00+01:00")
        assert dossier.ds_date_derniere_modification == expected_updated_at

    def test_update_updated_at_from_multiple_annotations_empty_list(self, dossier):
        """Test with empty annotations list"""
        ds_service = DsService()

        results = {
            "data": {
                "dossierModifierAnnotations": {
                    "annotations": [],
                    "errors": None,
                }
            }
        }

        original_date = timezone.make_aware(datetime(2025, 1, 1, 10, 0, 0))
        dossier.ds_date_derniere_modification = original_date
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        # Should not change if no annotations
        assert dossier.ds_date_derniere_modification == original_date

    def test_update_updated_at_from_multiple_annotations_missing_data(self, dossier):
        """Test with missing data structure"""
        ds_service = DsService()

        results = {"data": {}}

        original_date = timezone.make_aware(datetime(2025, 1, 1, 10, 0, 0))
        dossier.ds_date_derniere_modification = original_date
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        # Should not change if data structure is missing
        assert dossier.ds_date_derniere_modification == original_date

    def test_update_updated_at_from_multiple_annotations_missing_dossier_modifier(
        self, dossier
    ):
        """Test with missing dossierModifierAnnotations key"""
        ds_service = DsService()

        results = {"data": {"otherKey": "value"}}

        original_date = timezone.make_aware(datetime(2025, 1, 1, 10, 0, 0))
        dossier.ds_date_derniere_modification = original_date
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        # Should not change if dossierModifierAnnotations is missing
        assert dossier.ds_date_derniere_modification == original_date

    def test_update_updated_at_from_multiple_annotations_single_annotation(
        self, dossier
    ):
        """Test with a single annotation"""
        ds_service = DsService()

        results = {
            "data": {
                "dossierModifierAnnotations": {
                    "annotations": [
                        {"id": "1", "updatedAt": "2025-01-15T14:30:00+01:00"},
                    ],
                    "errors": None,
                }
            }
        }

        dossier.ds_date_derniere_modification = None
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        expected_updated_at = datetime.fromisoformat("2025-01-15T14:30:00+01:00")
        assert dossier.ds_date_derniere_modification == expected_updated_at

    def test_update_updated_at_from_multiple_annotations_updates_existing_date(
        self, dossier
    ):
        """Test that it updates an existing ds_date_derniere_modification"""
        ds_service = DsService()

        results = {
            "data": {
                "dossierModifierAnnotations": {
                    "annotations": [
                        {"id": "1", "updatedAt": "2025-01-20T15:45:00+01:00"},
                    ],
                    "errors": None,
                }
            }
        }

        old_date = timezone.make_aware(datetime(2025, 1, 1, 10, 0, 0))
        dossier.ds_date_derniere_modification = old_date
        dossier.save()

        ds_service._update_updated_at_from_multiple_annotations(dossier, results)

        dossier.refresh_from_db()
        expected_updated_at = datetime.fromisoformat("2025-01-20T15:45:00+01:00")
        assert dossier.ds_date_derniere_modification == expected_updated_at
        assert dossier.ds_date_derniere_modification != old_date


class TestUpdateAnnotations:
    def test_update_annotations_success_single_checkbox(self, user, dossier):
        """Test updating a single checkbox annotation"""
        ds_service = DsService()

        field_ids = {
            "annotations_is_qpv": "field_qpv_123",
        }

        mock_get_ds_field_id = MagicMock(
            side_effect=lambda dossier, field: field_ids[field]
        )

        with (
            patch.object(ds_service, "_get_ds_field_id", mock_get_ds_field_id),
            patch.object(ds_service, "mutator") as mock_mutator,
            patch.object(ds_service, "_check_results") as mock_check_results,
            patch.object(
                ds_service, "_update_updated_at_from_multiple_annotations"
            ) as mock_update_updated_at,
        ):
            mock_mutator.dossier_modifier_annotations.return_value = {
                "data": {
                    "dossierModifierAnnotations": {
                        "clientMutationId": "test",
                        "annotations": [
                            {
                                "id": "field_qpv_123",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            }
                        ],
                    }
                }
            }

            annotations_to_update = {"annotations_is_qpv": True}
            result = ds_service.update_annotations(
                dossier=dossier, user=user, annotations=annotations_to_update
            )

            # Verify _get_ds_field_id was called for each annotation
            assert mock_get_ds_field_id.call_count == 1
            mock_get_ds_field_id.assert_called_with(dossier, "annotations_is_qpv")

            # Verify mutator was called with correct parameters
            mock_mutator.dossier_modifier_annotations.assert_called_once()
            call_args = mock_mutator.dossier_modifier_annotations.call_args
            assert call_args[0][0] == dossier.ds_id  # dossier_id
            assert call_args[0][1] == user.ds_id  # user_id

            # Verify annotations structure
            annotations = call_args[0][2]
            assert len(annotations) == 1
            assert annotations[0] == {
                "id": "field_qpv_123",
                "value": {"checkbox": True},
            }

            # Verify _check_results was called
            mock_check_results.assert_called_once()
            check_call_args = mock_check_results.call_args[0]
            assert (
                check_call_args[0]
                == mock_mutator.dossier_modifier_annotations.return_value
            )
            assert check_call_args[1] == dossier
            assert check_call_args[2] == user
            assert check_call_args[3] == "annotations"
            assert mock_check_results.call_args[1] == {"value": annotations}

            # Verify _update_updated_at_from_multiple_annotations was called
            mock_update_updated_at.assert_called_once_with(
                dossier, mock_mutator.dossier_modifier_annotations.return_value
            )

            # Verify return value
            assert result == mock_mutator.dossier_modifier_annotations.return_value

    def test_update_annotations_success_multiple_checkboxes(self, user, dossier):
        """Test updating multiple checkbox annotations"""
        ds_service = DsService()

        field_ids = {
            "annotations_is_qpv": "field_qpv_123",
            "annotations_is_crte": "field_crte_456",
            "annotations_is_budget_vert": "field_budget_vert_789",
            "annotations_is_frr": "field_frr_101",
            "annotations_is_acv": "field_acv_102",
            "annotations_is_pvd": "field_pvd_103",
            "annotations_is_va": "field_va_104",
            "annotations_is_autre_zonage_local": "field_autre_zonage_local_105",
            "annotations_is_contrat_local": "field_contrat_local_106",
        }

        mock_get_ds_field_id = MagicMock(
            side_effect=lambda dossier, field: field_ids[field]
        )

        with (
            patch.object(ds_service, "_get_ds_field_id", mock_get_ds_field_id),
            patch.object(ds_service, "mutator") as mock_mutator,
            patch.object(ds_service, "_check_results"),
            patch.object(ds_service, "_update_updated_at_from_multiple_annotations"),
        ):
            mock_mutator.dossier_modifier_annotations.return_value = {
                "data": {
                    "dossierModifierAnnotations": {
                        "clientMutationId": "test",
                        "annotations": [
                            {
                                "id": "field_qpv_123",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_crte_456",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_budget_vert_789",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_frr_101",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_acv_102",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_pvd_103",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_va_104",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_autre_zonage_local_105",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_contrat_local_106",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_autre_zonage_local_105",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_contrat_local_106",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                        ],
                    }
                }
            }

            annotations_to_update = {
                "annotations_is_qpv": True,
                "annotations_is_crte": False,
                "annotations_is_budget_vert": True,
                "annotations_is_frr": False,
                "annotations_is_acv": True,
                "annotations_is_pvd": False,
                "annotations_is_va": True,
                "annotations_is_autre_zonage_local": False,
                "annotations_is_contrat_local": True,
            }
            ds_service.update_annotations(
                dossier=dossier, user=user, annotations=annotations_to_update
            )

            # Verify _get_ds_field_id was called for each annotation
            assert mock_get_ds_field_id.call_count == 9
            assert mock_get_ds_field_id.call_args_list[0][0] == (
                dossier,
                "annotations_is_qpv",
            )
            assert mock_get_ds_field_id.call_args_list[1][0] == (
                dossier,
                "annotations_is_crte",
            )
            assert mock_get_ds_field_id.call_args_list[2][0] == (
                dossier,
                "annotations_is_budget_vert",
            )
            assert mock_get_ds_field_id.call_args_list[3][0] == (
                dossier,
                "annotations_is_frr",
            )
            assert mock_get_ds_field_id.call_args_list[4][0] == (
                dossier,
                "annotations_is_acv",
            )
            assert mock_get_ds_field_id.call_args_list[5][0] == (
                dossier,
                "annotations_is_pvd",
            )
            assert mock_get_ds_field_id.call_args_list[6][0] == (
                dossier,
                "annotations_is_va",
            )
            assert mock_get_ds_field_id.call_args_list[7][0] == (
                dossier,
                "annotations_is_autre_zonage_local",
            )
            assert mock_get_ds_field_id.call_args_list[8][0] == (
                dossier,
                "annotations_is_contrat_local",
            )

            # Verify annotations structure
            call_args = mock_mutator.dossier_modifier_annotations.call_args
            annotations = call_args[0][2]
            assert len(annotations) == 9

            # Verify annotations are in the correct format
            annotation_dict = {
                ann["id"]: ann["value"]["checkbox"] for ann in annotations
            }
            assert annotation_dict["field_qpv_123"] is True
            assert annotation_dict["field_crte_456"] is False
            assert annotation_dict["field_budget_vert_789"] is True
            assert annotation_dict["field_frr_101"] is False
            assert annotation_dict["field_acv_102"] is True
            assert annotation_dict["field_pvd_103"] is False
            assert annotation_dict["field_va_104"] is True
            assert annotation_dict["field_autre_zonage_local_105"] is False
            assert annotation_dict["field_contrat_local_106"] is True
            assert annotation_dict["field_autre_zonage_local_105"] is False

    def test_update_annotations_annotations_dict_structure(self, user, dossier):
        """Test that annotations dict is built correctly with proper structure"""
        ds_service = DsService()

        field_ids = {
            "annotations_is_qpv": "field_qpv_123",
            "annotations_is_crte": "field_crte_456",
        }

        def mock_get_ds_field_id(dossier, field):
            return field_ids[field]

        with (
            patch.object(
                ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id
            ),
            patch.object(ds_service, "mutator") as mock_mutator,
            patch.object(ds_service, "_check_results"),
            patch.object(ds_service, "_update_updated_at_from_multiple_annotations"),
        ):
            mock_mutator.dossier_modifier_annotations.return_value = {
                "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
            }

            annotations_to_update = {
                "annotations_is_qpv": True,
                "annotations_is_crte": False,
            }
            ds_service.update_annotations(
                dossier=dossier, user=user, annotations=annotations_to_update
            )

            # Verify annotations structure
            call_args = mock_mutator.dossier_modifier_annotations.call_args
            annotations = call_args[0][2]

            # Check structure of each annotation
            for annotation in annotations:
                assert "id" in annotation
                assert "value" in annotation
                assert "checkbox" in annotation["value"]
                assert isinstance(annotation["value"]["checkbox"], bool)

            # Verify specific values
            assert annotations[0]["id"] == "field_qpv_123"
            assert annotations[0]["value"]["checkbox"] is True
            assert annotations[1]["id"] == "field_crte_456"
            assert annotations[1]["value"]["checkbox"] is False

    def test_update_annotations_calls_helper_methods(self, user, dossier):
        """Test that all helper methods are called correctly"""
        ds_service = DsService()

        field_ids = {
            "annotations_is_qpv": "field_qpv_123",
        }

        def mock_get_ds_field_id(dossier, field):
            return field_ids[field]

        with (
            patch.object(
                ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id
            ) as mock_get_field_id,
            patch.object(ds_service, "mutator") as mock_mutator,
            patch.object(ds_service, "_check_results") as mock_check_results,
            patch.object(
                ds_service, "_update_updated_at_from_multiple_annotations"
            ) as mock_update_updated_at,
        ):
            mock_response = {
                "data": {
                    "dossierModifierAnnotations": {
                        "clientMutationId": "test",
                        "annotations": [
                            {
                                "id": "field_qpv_123",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            }
                        ],
                    }
                }
            }
            mock_mutator.dossier_modifier_annotations.return_value = mock_response

            annotations_to_update = {"annotations_is_qpv": True}
            ds_service.update_annotations(
                dossier=dossier, user=user, annotations=annotations_to_update
            )

            # Verify _get_ds_field_id was called
            mock_get_field_id.assert_called()

            # Verify mutator was called with correct dossier and user IDs
            mock_mutator.dossier_modifier_annotations.assert_called_once()
            call_args = mock_mutator.dossier_modifier_annotations.call_args
            assert call_args[0][0] == dossier.ds_id
            assert call_args[0][1] == user.ds_id

            # Verify _check_results was called with correct parameters
            mock_check_results.assert_called_once()
            check_call_args = mock_check_results.call_args
            assert check_call_args[0][0] == mock_response
            assert check_call_args[0][1] == dossier
            assert check_call_args[0][2] == user
            assert check_call_args[0][3] == "annotations"

            # Verify _update_updated_at_from_multiple_annotations was called
            mock_update_updated_at.assert_called_once_with(dossier, mock_response)

    def test_update_annotations_infers_checkbox_and_text_from_field_type(
        self, user, dossier
    ):
        """A single annotations dict is split into checkbox/text values based on
        the matching Dossier model field type."""
        ds_service = DsService()

        field_ids = {
            "annotations_is_autre_zonage_local": "field_autre_zonage_local_checkbox_123",
            "annotations_autre_zonage_local": "field_autre_zonage_local_text_456",
            "annotations_is_contrat_local": "field_contrat_local_checkbox_789",
            "annotations_contrat_local": "field_contrat_local_text_101",
        }

        mock_get_ds_field_id = MagicMock(
            side_effect=lambda dossier, field: field_ids[field]
        )

        with (
            patch.object(ds_service, "_get_ds_field_id", mock_get_ds_field_id),
            patch.object(ds_service, "mutator") as mock_mutator,
            patch.object(ds_service, "_check_results"),
            patch.object(ds_service, "_update_updated_at_from_multiple_annotations"),
        ):
            mock_mutator.dossier_modifier_annotations.return_value = {
                "data": {
                    "dossierModifierAnnotations": {
                        "clientMutationId": "test",
                        "annotations": [
                            {
                                "id": "field_autre_zonage_local_checkbox_123",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_autre_zonage_local_text_456",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_contrat_local_checkbox_789",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                            {
                                "id": "field_contrat_local_text_101",
                                "updatedAt": "2025-01-15T10:30:00+00:00",
                            },
                        ],
                    }
                }
            }

            annotations = {
                "annotations_is_autre_zonage_local": True,
                "annotations_autre_zonage_local": "Zonage Test ABC",
                "annotations_is_contrat_local": True,
                "annotations_contrat_local": "Contrat Test XYZ",
            }
            ds_service.update_annotations(
                dossier=dossier, user=user, annotations=annotations
            )

            # Verify _get_ds_field_id was called for all annotations (checkboxes + text)
            assert mock_get_ds_field_id.call_count == 4

            # Verify annotations structure
            call_args = mock_mutator.dossier_modifier_annotations.call_args
            annotations = call_args[0][2]
            assert len(annotations) == 4

            # Verify checkbox annotations
            checkbox_annotations = [
                ann for ann in annotations if "checkbox" in ann["value"]
            ]
            assert len(checkbox_annotations) == 2
            checkbox_dict = {
                ann["id"]: ann["value"]["checkbox"] for ann in checkbox_annotations
            }
            assert checkbox_dict["field_autre_zonage_local_checkbox_123"] is True
            assert checkbox_dict["field_contrat_local_checkbox_789"] is True

            # Verify text annotations
            text_annotations = [ann for ann in annotations if "text" in ann["value"]]
            assert len(text_annotations) == 2
            text_dict = {ann["id"]: ann["value"]["text"] for ann in text_annotations}
            assert text_dict["field_autre_zonage_local_text_456"] == "Zonage Test ABC"
            assert text_dict["field_contrat_local_text_101"] == "Contrat Test XYZ"


class TestTransformMessage:
    def test_transform_message_known_phrases(self):
        ds = DsService()
        messages = ["Le dossier est déjà en\xa0construction"]
        out = ds._transform_message(messages)
        assert "Le dossier est en construction sur Démarche Numérique." in out

    def test_transform_message_permission_phrase(self):
        ds = DsService()
        messages = ["An object of type Dossier was hidden due to permissions"]
        out = ds._transform_message(messages)
        assert "Vous n'avez pas accès à ce dossier." in out

    def test_transform_message_generic(self):
        ds = DsService()
        messages = ["Une erreur"]
        out = ds._transform_message(messages)
        assert out == "Une erreur"

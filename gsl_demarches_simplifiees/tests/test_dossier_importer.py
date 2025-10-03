import logging
from unittest.mock import MagicMock, patch

import pytest
from django.contrib import messages
from django.utils.timezone import datetime

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier import (
    save_one_dossier_from_ds,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory


def test_save_one_dossier_from_ds_error_with_invalid_ds_response():
    ds_client = DsClient()
    dossier = DossierFactory.build()
    with patch.object(
        ds_client,
        "get_one_dossier",
        return_value={"no_date_in_result": "so_raise_an_exception"},
    ):
        with pytest.raises(DsServiceException):
            save_one_dossier_from_ds(dossier, ds_client)


def test_save_one_dossier_from_ds_no_need_to_update():
    ds_client = DsClient()
    date_in_ds_and_dossier = "2024-10-16T10:09:33+02:00"
    dossier = DossierFactory.build(
        ds_date_derniere_modification=datetime.fromisoformat(date_in_ds_and_dossier)
    )
    with patch.object(
        ds_client,
        "get_one_dossier",
        return_value={"dateDerniereModification": date_in_ds_and_dossier},
    ):
        level, message = save_one_dossier_from_ds(dossier, ds_client)
        assert level == messages.WARNING
        assert "Le dossier était déjà à jour sur Turgot" in message


def test_save_one_dossier_from_ds_should_be_updated():
    ds_client = DsClient()
    date_in_ds = "2025-10-16T10:09:33+02:00"
    date_in_turgot = "2024-10-16T10:09:33+02:00"
    dossier = DossierFactory.build(
        ds_date_derniere_modification=datetime.fromisoformat(date_in_turgot)
    )
    with patch.object(
        ds_client,
        "get_one_dossier",
        return_value={"dateDerniereModification": date_in_ds},
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ) as target_task:
            level, message = save_one_dossier_from_ds(dossier, ds_client)
            assert level == messages.SUCCESS
            assert "Le dossier a bien été mis à jour" in message
            target_task.assert_called_once()


def test_launch_graphql_query_token_error_logs_and_raises(caplog):
    error_response = {
        "errors": [
            {
                "message": "Without a token, only persisted queries are allowed",
                "extensions": {"code": "forbidden"},
            }
        ],
        "data": None,
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.json.return_value = error_response
    mock_resp.text = str(error_response)

    with patch("requests.post", return_value=mock_resp):
        client = DsClient()
        with caplog.at_level(logging.CRITICAL):
            with pytest.raises(Exception) as excinfo:
                client.launch_graphql_query("someOperation")
            assert (
                "HTTP Error while running query. Status code: 403. Error: {'errors': [{'message': 'Without a token, only persisted queries are allowed', 'extensions': {'code': 'forbidden'}}], 'data': None}"
                in str(excinfo.value)
            )
            assert "DS forbidden access : token problem ?" in caplog.text

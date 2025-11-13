import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import responses
from django.conf import settings

from gsl_demarches_simplifiees.ds_client import DsClient


@responses.activate
def test_launch_graphql_query_token_error_logs_and_raises(caplog):
    responses.add(
        responses.POST,
        settings.DS_API_URL,
        json={
            "errors": [
                {
                    "message": "Without a token, only persisted queries are allowed",
                    "extensions": {"code": "forbidden"},
                }
            ],
            "data": None,
        },
        status=403,
    )

    client = DsClient()
    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(Exception) as excinfo:
            client.launch_graphql_query("someOperation")
        assert "Nous n'arrivons pas à nous connecter à Démarches Simplifiées." in str(
            excinfo.value
        )
        assert "DS forbidden access : token problem ?" in caplog.text


def test_get_demarche_dossiers_with_updated_since_calls_graphql_with_iso_format():
    """Test that get_demarche_dossiers converts datetime to ISO format for GraphQL query."""
    client = DsClient()
    demarche_number = 123
    updated_since = datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
    expected_iso_format = updated_since.isoformat()

    mock_response = {
        "data": {
            "demarche": {
                "dossiers": {
                    "nodes": [{"id": "DOSS-1", "number": 20240001}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }

    with patch.object(
        client, "launch_graphql_query", return_value=mock_response
    ) as mock_query:
        list(client.get_demarche_dossiers(demarche_number, updated_since=updated_since))

        # Verify the query was called
        assert mock_query.call_count == 1

        # Verify the variables passed to the query
        call_args = mock_query.call_args
        assert call_args[0][0] == "getDemarche"  # operation_name
        variables = call_args[1]["variables"]

        assert variables["demarcheNumber"] == demarche_number
        assert variables["includeDossiers"] is True
        assert variables["updatedSince"] == expected_iso_format
        # Verify it's a string in ISO format
        assert isinstance(variables["updatedSince"], str)
        assert "T" in variables["updatedSince"]  # ISO format contains 'T'


def test_get_demarche_dossiers_without_updated_since_passes_none():
    """Test that get_demarche_dossiers passes None when updated_since is not provided."""
    client = DsClient()
    demarche_number = 123

    mock_response = {
        "data": {
            "demarche": {
                "dossiers": {
                    "nodes": [{"id": "DOSS-1", "number": 20240001}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }

    with patch.object(
        client, "launch_graphql_query", return_value=mock_response
    ) as mock_query:
        list(client.get_demarche_dossiers(demarche_number))

        # Verify the query was called
        assert mock_query.call_count == 1

        # Verify the variables passed to the query
        call_args = mock_query.call_args
        variables = call_args[1]["variables"]

        assert variables["demarcheNumber"] == demarche_number
        assert variables["includeDossiers"] is True
        assert variables["updatedSince"] is None

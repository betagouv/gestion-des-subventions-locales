import logging
from unittest.mock import patch

import pytest
import responses
from django.conf import settings
from django.utils import timezone

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
        assert "Nous n'arrivons pas à nous connecter à Démarche Numérique." in str(
            excinfo.value
        )
        assert "DN forbidden access : token problem ?" in caplog.text


def test_get_demarche_dossiers_with_updated_since_calls_graphql_with_iso_format():
    """Test that get_demarche_dossiers converts datetime to ISO format for GraphQL query."""
    client = DsClient()
    demarche_number = 123
    updated_since = timezone.datetime(2024, 1, 15)
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


def test_iter_demarche_dossiers_pages_with_after_cursor():
    """Test that iter_demarche_dossiers_pages passes after_cursor in variables."""
    client = DsClient()
    demarche_number = 123
    after_cursor = "abc123cursor=="

    mock_response = {
        "data": {
            "demarche": {
                "dossiers": {
                    "nodes": [{"id": "DOSS-1", "number": 20240001}],
                    "pageInfo": {"hasNextPage": False, "endCursor": "xyz789"},
                }
            }
        }
    }

    with patch.object(
        client, "launch_graphql_query", return_value=mock_response
    ) as mock_query:
        pages = list(
            client.iter_demarche_dossiers_pages(
                demarche_number, after_cursor=after_cursor
            )
        )

        assert mock_query.call_count == 1
        variables = mock_query.call_args[1]["variables"]
        assert variables["after"] == after_cursor
        assert variables["updatedSince"] is None

        assert len(pages) == 1
        nodes, end_cursor = pages[0]
        assert nodes == [{"id": "DOSS-1", "number": 20240001}]
        assert end_cursor == "xyz789"


def test_iter_demarche_dossiers_pages_paginates_until_no_next_page():
    """Test that iter_demarche_dossiers_pages follows pagination until hasNextPage is False."""
    client = DsClient()
    demarche_number = 123

    page1_response = {
        "data": {
            "demarche": {
                "dossiers": {
                    "nodes": [{"id": "DOSS-1", "number": 1}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_page1"},
                }
            }
        }
    }
    page2_response = {
        "data": {
            "demarche": {
                "dossiers": {
                    "nodes": [{"id": "DOSS-2", "number": 2}],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor_page2"},
                }
            }
        }
    }

    with patch.object(
        client,
        "launch_graphql_query",
        side_effect=[page1_response, page2_response],
    ) as mock_query:
        pages = list(client.iter_demarche_dossiers_pages(demarche_number))

        assert mock_query.call_count == 2
        # Second call should use endCursor from first page
        second_call_variables = mock_query.call_args_list[1][1]["variables"]
        assert second_call_variables["after"] == "cursor_page1"

        assert len(pages) == 2
        assert pages[0] == ([{"id": "DOSS-1", "number": 1}], "cursor_page1")
        assert pages[1] == ([{"id": "DOSS-2", "number": 2}], "cursor_page2")

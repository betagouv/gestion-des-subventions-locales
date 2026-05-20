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


def _make_fetch_page_response(dossiers=None, pending_deleted=None, deleted=None):
    def _stream(nodes=None):
        return {
            "nodes": nodes or [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }

    return {
        "data": {
            "demarche": {
                "dossiers": _stream(dossiers),
                "pendingDeletedDossiers": _stream(pending_deleted),
                "deletedDossiers": _stream(deleted),
            }
        }
    }


def test_fetch_demarche_page_converts_datetime_to_iso_format():
    client = DsClient()
    updated_since = timezone.datetime(2024, 1, 15)

    with patch.object(
        client, "launch_graphql_query", return_value=_make_fetch_page_response()
    ) as mock_query:
        client.fetch_demarche_page(123, updated_since=updated_since)

        variables = mock_query.call_args[1]["variables"]
        assert variables["updatedSince"] == updated_since.isoformat()
        assert "T" in variables["updatedSince"]


def test_fetch_demarche_page_passes_none_when_no_updated_since():
    client = DsClient()

    with patch.object(
        client, "launch_graphql_query", return_value=_make_fetch_page_response()
    ) as mock_query:
        client.fetch_demarche_page(123)

        variables = mock_query.call_args[1]["variables"]
        assert variables["updatedSince"] is None


def test_fetch_demarche_page_passes_cursors_and_include_flags():
    client = DsClient()

    with patch.object(
        client, "launch_graphql_query", return_value=_make_fetch_page_response()
    ) as mock_query:
        client.fetch_demarche_page(
            123,
            dossiers_after="cursor-d",
            pending_deleted_after="cursor-p",
            deleted_after="cursor-del",
            include_dossiers=True,
            include_pending_deleted=False,
            include_deleted=True,
        )

        variables = mock_query.call_args[1]["variables"]
        assert variables["demarcheNumber"] == 123
        assert variables["after"] == "cursor-d"
        assert variables["pendingDeletedAfter"] == "cursor-p"
        assert variables["deletedAfter"] == "cursor-del"
        assert variables["includeDossiers"] is True
        assert variables["includePendingDeletedDossiers"] is False
        assert variables["includeDeletedDossiers"] is True


def test_fetch_demarche_page_respects_page_size():
    client = DsClient()

    with patch.object(
        client, "launch_graphql_query", return_value=_make_fetch_page_response()
    ) as mock_query:
        client.fetch_demarche_page(123, page_size=20)

        variables = mock_query.call_args[1]["variables"]
        assert variables["first"] == 20
        assert variables["pendingDeletedFirst"] == 20
        assert variables["deletedFirst"] == 20


def test_fetch_demarche_page_returns_demarche_data():
    client = DsClient()
    nodes = [{"id": "DOSS-1", "number": 20240001}]

    with patch.object(
        client,
        "launch_graphql_query",
        return_value=_make_fetch_page_response(dossiers=nodes),
    ):
        result = client.fetch_demarche_page(123)

        assert result["dossiers"]["nodes"] == nodes
        assert result["dossiers"]["pageInfo"]["hasNextPage"] is False

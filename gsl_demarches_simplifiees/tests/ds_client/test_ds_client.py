import logging

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

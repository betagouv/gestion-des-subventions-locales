import logging
from unittest.mock import MagicMock, patch

import pytest

from gsl_demarches_simplifiees.ds_client import DsClient


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

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from gsl_demarches_simplifiees.tests.factories import (
    DemarcheFactory,
    ProfileFactory,
)
from gsl_ds_proxy.tests.factories import ProxyTokenFactory


def _read_stream(response):
    return b"".join(response.streaming_content)


def _parse_stream(response):
    return json.loads(_read_stream(response).lstrip())


@override_settings(DS_API_TOKEN="test-ds-token", DS_API_URL="https://ds.test/graphql")
class GraphqlProxyViewTest(TestCase):
    def setUp(self):
        self.profile = ProfileFactory(ds_id="inst-a")
        self.demarche = DemarcheFactory(ds_number=123)
        self.token = ProxyTokenFactory(demarche=self.demarche)
        self.token.instructeurs.add(self.profile)
        self.url = "/ds-proxy/graphql/"
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token.plaintext_key}"}

    def _get_demarche_payload(self, demarche_number=None):
        return {
            "query": "query getDemarche { demarche { title } }",
            "operationName": "getDemarche",
            "variables": {"demarcheNumber": demarche_number or self.demarche.ds_number},
        }

    def _post(self, data, **extra_headers):
        headers = {**self.headers, **extra_headers}
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
            **headers,
        )

    def test_missing_auth_header(self):
        response = self.client.post(
            self.url,
            data=json.dumps(self._get_demarche_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_token(self):
        response = self.client.post(
            self.url,
            data=json.dumps(self._get_demarche_payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )
        self.assertEqual(response.status_code, 401)

    def test_inactive_token(self):
        self.token.is_active = False
        self.token.save()
        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 401)

    def test_invalid_json(self):
        response = self.client.post(
            self.url,
            data="not json",
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_mutation_rejected(self):
        response = self._post({"query": "mutation { dossierAccepter { id } }"})
        self.assertEqual(response.status_code, 403)

    def test_get_method_rejected(self):
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, 405)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_successful_proxy(self, mock_post):
        ds_response_data = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "number": 1,
                                "groupeInstructeur": {
                                    "instructeurs": [
                                        {"id": "inst-a", "email": "a@t.fr"}
                                    ]
                                },
                                "instructeurs": [],
                            },
                            {
                                "number": 2,
                                "groupeInstructeur": {
                                    "instructeurs": [
                                        {"id": "inst-b", "email": "b@t.fr"}
                                    ]
                                },
                                "instructeurs": [],
                            },
                        ],
                    },
                }
            }
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = ds_response_data

        response = self._post(
            {
                "query": "query getDemarche { demarche { dossiers { nodes { number } } } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )

        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        nodes = data["data"]["demarche"]["dossiers"]["nodes"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["number"], 1)

        # Verify DS was called with the right token
        call_kwargs = mock_post.call_args
        self.assertEqual(
            call_kwargs.kwargs["headers"]["Authorization"],
            "Bearer test-ds-token",
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_ds_connection_error(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError()

        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(
            data,
            {"errors": [{"message": "Erreur de connexion à Démarches Simplifiées."}]},
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_ds_http_error(self, mock_post):
        import requests as req

        mock_post.return_value.status_code = 500
        mock_post.return_value.raise_for_status.side_effect = req.exceptions.HTTPError()

        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(
            data,
            {"errors": [{"message": "Erreur de Démarches Simplifiées."}]},
        )

    def test_getDemarche_wrong_demarche_number_rejected(self):
        response = self._post(self._get_demarche_payload(demarche_number=999))
        self.assertEqual(response.status_code, 403)

    def test_getDemarche_missing_variables_rejected(self):
        response = self._post(
            {
                "query": "query getDemarche { demarche { title } }",
                "operationName": "getDemarche",
            }
        )
        self.assertEqual(response.status_code, 403)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDossier_of_token_demarche_allowed(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "dossier": {
                    "number": 42,
                    "demarche": {"number": self.demarche.ds_number},
                }
            }
        }

        response = self._post(
            {
                "query": "query getDossier { dossier { number } }",
                "operationName": "getDossier",
                "variables": {"dossierNumber": 42},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertIn("data", data)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDossier_of_other_demarche_rejected(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "dossier": {
                    "number": 42,
                    "demarche": {"number": 999},
                }
            }
        }

        response = self._post(
            {
                "query": "query getDossier { dossier { number } }",
                "operationName": "getDossier",
                "variables": {"dossierNumber": 42},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertIn("errors", data)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDossier_without_demarche_in_response_rejected(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"data": {"dossier": {"number": 42}}}

        response = self._post(
            {
                "query": "query getDossier { dossier { number } }",
                "operationName": "getDossier",
                "variables": {"dossierNumber": 42},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertIn("errors", data)

    def test_getGroupeInstructeur_rejected(self):
        response = self._post(
            {
                "query": "query getGroupeInstructeur { groupeInstructeur { id } }",
                "operationName": "getGroupeInstructeur",
                "variables": {"groupeInstructeurNumber": 1},
            }
        )
        self.assertEqual(response.status_code, 403)

    def test_unknown_operation_rejected(self):
        response = self._post(
            {
                "query": "query foo { foo }",
                "operationName": "foo",
            }
        )
        self.assertEqual(response.status_code, 403)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDemarche_response_with_wrong_demarche_number_rejected(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": 999,
                    "dossiers": {"nodes": []},
                }
            }
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertIn("errors", data)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDemarche_response_without_number_field_rejected(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {"demarche": {"dossiers": {"nodes": []}}}
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { dossiers { nodes { number } } } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertIn("errors", data)

    def test_mutation_with_leading_whitespace_rejected(self):
        response = self._post({"query": "\n\n  mutation { dossierAccepter { id } }"})
        self.assertEqual(response.status_code, 403)

    def test_mutation_with_crlf_rejected(self):
        response = self._post({"query": "\r\nmutation { dossierAccepter { id } }"})
        self.assertEqual(response.status_code, 403)

    def test_mutation_with_leading_comment_rejected(self):
        response = self._post(
            {"query": "# a comment\nmutation { dossierAccepter { id } }"}
        )
        self.assertEqual(response.status_code, 403)

    def test_subscription_rejected(self):
        response = self._post({"query": "subscription { dossierUpdated { id } }"})
        self.assertEqual(response.status_code, 403)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_query_with_leading_comment_parsed(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {"nodes": []},
                }
            }
        }
        response = self._post(
            {
                "query": "# leading comment\nquery getDemarche { demarche { number } }",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(data["data"]["demarche"]["number"], self.demarche.ds_number)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_ds_timeout_returns_in_band_error(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout()

        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(
            data,
            {
                "errors": [
                    {"message": "Délai d'attente dépassé pour Démarches Simplifiées."}
                ]
            },
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_query_forwarded_verbatim(self, mock_post):
        """The proxy should not rewrite the query — it's forwarded as sent."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {"nodes": []},
                }
            }
        }

        query = (
            "query getDemarche { demarche { number dossiers { nodes "
            "{ number groupeInstructeur { instructeurs { id } } } } } }"
        )
        response = self._post(
            {
                "query": query,
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        # Drain the stream so the view has actually called DS.
        _read_stream(response)
        self.assertEqual(mock_post.call_args.kwargs["json"]["query"], query)

    def test_document_with_multiple_operations_requires_operationName(self):
        response = self._post(
            {
                "query": (
                    "query getDemarche { demarche { title } } "
                    "query getDossier { dossier { number } }"
                ),
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_document_with_only_fragments_rejected(self):
        response = self._post({"query": "fragment DossierFields on Dossier { number }"})
        self.assertEqual(response.status_code, 400)

    def test_shorthand_query_rejected_as_unknown_operation(self):
        response = self._post({"query": "{ demarche { title } }"})
        self.assertEqual(response.status_code, 403)

    def test_operationName_not_in_document_rejected(self):
        response = self._post(
            {
                "query": "query getDemarche { demarche { title } }",
                "operationName": "getSomethingElse",
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_malformed_graphql_returns_400(self):
        response = self._post(
            {
                "query": "query getDemarche { demarche { { } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 400)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_ds_post_called_with_timeout(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {"nodes": []},
                }
            }
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        _read_stream(response)
        self.assertEqual(mock_post.call_args.kwargs["timeout"], (5, 55))

    @patch("gsl_ds_proxy.views.requests.post")
    def test_first_byte_is_heartbeat_space(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {"nodes": []},
                }
            }
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        first_chunk = next(iter(response.streaming_content))
        self.assertEqual(first_chunk, b" ")

    @patch("gsl_ds_proxy.views.requests.post")
    def test_final_payload_is_valid_json_with_leading_heartbeat(self, mock_post):
        ds_data = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {"nodes": []},
                }
            }
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = ds_data

        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        stream_bytes = _read_stream(response)
        self.assertTrue(stream_bytes.startswith(b" "))
        self.assertEqual(json.loads(stream_bytes.lstrip()), ds_data)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_connection_error_during_streaming_yields_graphql_error_with_200(
        self, mock_post
    ):
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError()

        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(
            data["errors"][0]["message"],
            "Erreur de connexion à Démarches Simplifiées.",
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_scope_check_failure_during_streaming_yields_graphql_error_with_200(
        self, mock_post
    ):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": 999,
                    "dossiers": {"nodes": []},
                }
            }
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(
            data["errors"][0]["message"],
            "Opération non autorisée pour cette démarche. "
            "La requête doit inclure `demarche { number }`.",
        )

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from gsl_demarches_simplifiees.tests.factories import (
    DemarcheFactory,
)
from gsl_ds_proxy.tests.factories import ProxyTokenFactory


def _read_stream(response):
    return b"".join(response.streaming_content)


def _parse_stream(response):
    return json.loads(_read_stream(response).lstrip())


@override_settings(DS_API_TOKEN="test-ds-token", DS_API_URL="https://ds.test/graphql")
class GraphqlProxyViewTest(TestCase):
    def setUp(self):
        self.demarche = DemarcheFactory(ds_number=123)
        self.token = ProxyTokenFactory(
            demarche=self.demarche,
            groupe_instructeur_ds_id="GROUPE-1",
        )
        self.url = "/ds-proxy/graphql/"
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token.plaintext_key}"}

        # The per-token Redis lock is exercised on its own in
        # GraphqlProxyTokenLockTest; here we neutralise it (always acquired,
        # no-op release) so the rest of the suite doesn't need a live Redis.
        acquire_patcher = patch(
            "gsl_ds_proxy.views.acquire_token_lock", return_value=MagicMock()
        )
        self.mock_acquire = acquire_patcher.start()
        self.addCleanup(acquire_patcher.stop)
        release_patcher = patch("gsl_ds_proxy.views.release_token_lock")
        self.mock_release = release_patcher.start()
        self.addCleanup(release_patcher.stop)

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

    def test_unconfigured_token_returns_403(self):
        self.token.groupe_instructeur_ds_id = ""
        self.token.save()
        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content)
        self.assertEqual(body["errors"][0]["message"], "Token non configuré.")

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
                                "groupeInstructeur": {"id": "GROUPE-1"},
                            },
                            {
                                "number": 2,
                                "groupeInstructeur": {"id": "GROUPE-2"},
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
            data["errors"][0]["message"],
            "Erreur de connexion à Démarches Simplifiées.",
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
            data["errors"][0]["message"], "Erreur de Démarches Simplifiées."
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_upstream_errors_forwarded_when_data_null(self, mock_post):
        upstream = {
            "data": None,
            "errors": [{"message": "Field 'demaarche' doesn't exist on type 'Query'"}],
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = upstream

        response = self._post(self._get_demarche_payload())

        self.assertEqual(response.status_code, 200)
        raw = _read_stream(response).decode()
        errors = json.loads(raw)["errors"]
        self.assertIn(upstream["errors"][0], errors)
        self.assertNotIn("La requête doit inclure", raw)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_upstream_errors_forwarded_when_data_empty(self, mock_post):
        upstream = {
            "data": {},
            "errors": [{"message": "Field 'demaarche' doesn't exist on type 'Query'"}],
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = upstream

        response = self._post(self._get_demarche_payload())

        self.assertEqual(response.status_code, 200)
        raw = _read_stream(response).decode()
        errors = json.loads(raw)["errors"]
        self.assertIn(upstream["errors"][0], errors)
        self.assertNotIn("La requête doit inclure", raw)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_upstream_errors_forwarded_for_getDossier(self, mock_post):
        upstream = {
            "data": {"dossier": None},
            "errors": [{"message": "Dossier introuvable"}],
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = upstream

        response = self._post(
            {
                "query": "query getDossier { dossier { number } }",
                "operationName": "getDossier",
                "variables": {"dossierNumber": 42},
            }
        )

        self.assertEqual(response.status_code, 200)
        raw = _read_stream(response).decode()
        errors = json.loads(raw)["errors"]
        self.assertIn(upstream["errors"][0], errors)
        self.assertNotIn("La requête doit inclure", raw)

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

    def test_disallowed_root_field_rejected(self):
        response = self._post(
            {
                "query": "query foo { foo }",
                "operationName": "foo",
            }
        )
        self.assertEqual(response.status_code, 403)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_arbitrary_operation_name_allowed_when_root_field_is_demarche(
        self, mock_post
    ):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "title": "Une démarche",
                }
            }
        }
        response = self._post(
            {
                "query": (
                    "query getInformationsForAProcess { demarche { number title } }"
                ),
                "operationName": "getInformationsForAProcess",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(data["data"]["demarche"]["number"], self.demarche.ds_number)

    def test_root_field_alias_rejected(self):
        response = self._post(
            {
                "query": "query getDemarche { x: demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 403)

    def test_multiple_root_fields_rejected(self):
        response = self._post(
            {
                "query": ("query Combo { demarche { number } dossier { number } }"),
                "operationName": "Combo",
                "variables": {
                    "demarcheNumber": self.demarche.ds_number,
                    "dossierNumber": 42,
                },
            }
        )
        self.assertEqual(response.status_code, 403)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_introspection_query_allowed_with_arbitrary_name(self, mock_post):
        introspection_payload = {"data": {"__schema": {"types": [{"name": "Query"}]}}}
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = introspection_payload
        response = self._post(
            {
                "query": "query Whatever { __schema { types { name } } }",
                "operationName": "Whatever",
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(data, introspection_payload)

    def test_root_fragment_spread_rejected(self):
        response = self._post(
            {
                "query": (
                    "query Q { ...F } fragment F on Query { demarche { number } }"
                ),
                "operationName": "Q",
                "variables": {"demarcheNumber": self.demarche.ds_number},
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
            data["errors"][0]["message"],
            "Délai d'attente dépassé pour Démarches Simplifiées.",
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

    @patch("gsl_ds_proxy.views.requests.post")
    def test_shorthand_query_accepted(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "title": "Une démarche",
                }
            }
        }
        response = self._post(
            {
                "query": "{ demarche { number title } }",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertEqual(data["data"]["demarche"]["number"], self.demarche.ds_number)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDemarche_groupeInstructeurs_field_rejected(self, mock_post):
        response = self._post(
            {
                "query": (
                    "query getDemarche { demarche "
                    "{ groupeInstructeurs { instructeurs { id } } } }"
                ),
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(mock_post.called)
        body = json.loads(response.content)
        self.assertEqual(
            body["errors"][0]["message"],
            "Champ démarche non autorisé : `groupeInstructeurs`.",
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDossier_demarche_groupeInstructeurs_field_rejected(self, mock_post):
        response = self._post(
            {
                "query": (
                    "query getDossier { dossier { number demarche "
                    "{ groupeInstructeurs { id } } } }"
                ),
                "operationName": "getDossier",
                "variables": {"dossierNumber": 42},
            }
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(mock_post.called)
        body = json.loads(response.content)
        self.assertEqual(
            body["errors"][0]["message"],
            "Champ démarche non autorisé : `groupeInstructeurs`.",
        )

    @patch("gsl_ds_proxy.views.requests.post")
    def test_getDemarche_allowed_fields_pass(self, mock_post):
        ds_response_data = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "title": "Une démarche",
                    "state": "publiee",
                    "dateCreation": "2025-01-01T00:00:00Z",
                    "dateFermeture": None,
                    "dossiers": {"nodes": []},
                }
            }
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = ds_response_data

        response = self._post(
            {
                "query": (
                    "query getDemarche { demarche "
                    "{ number title state dateCreation dateFermeture "
                    "dossiers { nodes { number } } } }"
                ),
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 200)
        data = _parse_stream(response)
        self.assertTrue(mock_post.called)
        self.assertEqual(data["data"]["demarche"]["title"], "Une démarche")

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

    # ------------------------------------------------------------------
    # request_id propagation
    # ------------------------------------------------------------------

    @staticmethod
    def _request_ids(errors):
        return [
            e.get("extensions", {}).get("requestId")
            for e in errors
            if e.get("extensions", {}).get("requestId")
        ]

    def test_request_id_in_401_response(self):
        response = self.client.post(
            self.url,
            data=json.dumps(self._get_demarche_payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )
        self.assertEqual(response.status_code, 401)
        body = json.loads(response.content)
        request_ids = self._request_ids(body["errors"])
        self.assertEqual(len(request_ids), 1)
        self.assertTrue(request_ids[0])

    def test_request_id_in_unconfigured_token_403(self):
        self.token.groupe_instructeur_ds_id = ""
        self.token.save()
        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content)
        self.assertTrue(
            body["errors"][0]["extensions"]["requestId"],
        )

    def test_request_id_in_invalid_json_response(self):
        response = self.client.post(
            self.url,
            data="not json",
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertTrue(body["errors"][0]["extensions"]["requestId"])

    def test_request_id_in_malformed_graphql_response(self):
        response = self._post(
            {
                "query": "query getDemarche { demarche { { } }",
                "operationName": "getDemarche",
            }
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertTrue(body["errors"][0]["extensions"]["requestId"])

    def test_request_id_in_mutation_rejection(self):
        response = self._post({"query": "mutation { dossierAccepter { id } }"})
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content)
        self.assertTrue(body["errors"][0]["extensions"]["requestId"])

    def test_request_id_in_forbidden_demarche_field(self):
        response = self._post(
            {
                "query": (
                    "query getDemarche { demarche "
                    "{ groupeInstructeurs { instructeurs { id } } } }"
                ),
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content)
        self.assertTrue(body["errors"][0]["extensions"]["requestId"])

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_id_in_streamed_ds_http_error(self, mock_post):
        import requests as req

        mock_post.return_value.status_code = 502
        mock_post.return_value.raise_for_status.side_effect = req.exceptions.HTTPError()

        response = self._post(self._get_demarche_payload())
        data = _parse_stream(response)
        self.assertTrue(data["errors"][0]["extensions"]["requestId"])

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_id_in_streamed_timeout(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout()

        response = self._post(self._get_demarche_payload())
        data = _parse_stream(response)
        self.assertTrue(data["errors"][0]["extensions"]["requestId"])

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_id_in_streamed_connection_error(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError()

        response = self._post(self._get_demarche_payload())
        data = _parse_stream(response)
        self.assertTrue(data["errors"][0]["extensions"]["requestId"])

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_id_in_scope_error_after_response(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {"demarche": {"number": 999, "dossiers": {"nodes": []}}}
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        data = _parse_stream(response)
        request_ids = self._request_ids(data["errors"])
        self.assertEqual(len(request_ids), 1)
        self.assertTrue(request_ids[0])

    # ------------------------------------------------------------------
    # Upstream DS errors preserved with scope error
    # ------------------------------------------------------------------

    @patch("gsl_ds_proxy.views.requests.post")
    def test_scope_error_preserves_upstream_ds_errors(self, mock_post):
        """When DS returns partial errors AND data fails scope check, both
        the upstream errors and our scope rejection are returned."""
        upstream_errors = [
            {
                "message": "Timeout on PersonneMorale.entreprise",
                "path": ["demarche", "dossiers", "nodes", 3, "demandeur", "entreprise"],
            },
            {
                "message": "Timeout on GroupeInstructeur.id",
                "path": ["demarche", "dossiers", "nodes", 7, "groupeInstructeur", "id"],
            },
        ]
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {"demarche": {"number": 999, "dossiers": {"nodes": []}}},
            "errors": upstream_errors,
        }
        response = self._post(
            {
                "query": "query getDemarche { demarche { number } }",
                "operationName": "getDemarche",
                "variables": {"demarcheNumber": self.demarche.ds_number},
            }
        )
        data = _parse_stream(response)
        self.assertIn(upstream_errors[0], data["errors"])
        self.assertIn(upstream_errors[1], data["errors"])
        scope_messages = [
            e["message"]
            for e in data["errors"]
            if "La requête doit inclure" in e["message"]
        ]
        self.assertEqual(len(scope_messages), 1)
        self.assertIsNone(data["data"])

    @patch("gsl_ds_proxy.views.requests.post")
    def test_verbatim_forward_prepends_request_id_marker(self, mock_post):
        """DS errors + null data: forward verbatim AND add our request_id
        marker so the partner can correlate with our logs."""
        upstream_errors = [
            {"message": "Field 'demaarche' doesn't exist on type 'Query'"},
        ]
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": None,
            "errors": upstream_errors,
        }

        response = self._post(self._get_demarche_payload())
        data = _parse_stream(response)

        self.assertIn(upstream_errors[0], data["errors"])
        marker_entries = [
            e for e in data["errors"] if e.get("extensions", {}).get("requestId")
        ]
        self.assertEqual(len(marker_entries), 1)
        self.assertTrue(marker_entries[0]["extensions"]["requestId"])

    # ------------------------------------------------------------------
    # Logging enrichment
    # ------------------------------------------------------------------

    @patch("gsl_ds_proxy.views.requests.post")
    def test_logging_extra_on_connection_error(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError()

        with self.assertLogs("gsl_ds_proxy.views", level="ERROR") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        record = cm.records[-1]
        self.assertEqual(record.proxy_token_id, self.token.id)
        self.assertEqual(record.demarche_number, self.demarche.ds_number)
        self.assertTrue(record.request_id)
        self.assertIsInstance(record.elapsed_ms, int)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_logging_extra_on_timeout(self, mock_post):
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout()

        with self.assertLogs("gsl_ds_proxy.views", level="ERROR") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        record = cm.records[-1]
        self.assertEqual(record.proxy_token_id, self.token.id)
        self.assertEqual(record.demarche_number, self.demarche.ds_number)
        self.assertTrue(record.request_id)
        self.assertIsInstance(record.elapsed_ms, int)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_logging_extra_on_http_error(self, mock_post):
        import requests as req

        mock_post.return_value.status_code = 503
        mock_post.return_value.raise_for_status.side_effect = req.exceptions.HTTPError()

        with self.assertLogs("gsl_ds_proxy.views", level="ERROR") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        record = cm.records[-1]
        self.assertEqual(record.proxy_token_id, self.token.id)
        self.assertEqual(record.demarche_number, self.demarche.ds_number)
        self.assertEqual(record.ds_status, 503)
        self.assertTrue(record.request_id)
        self.assertIsInstance(record.elapsed_ms, int)

    # ------------------------------------------------------------------
    # Per-request structured log
    # ------------------------------------------------------------------

    @staticmethod
    def _request_log_records(records):
        return [r for r in records if r.getMessage() == "DS proxy: request"]

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_on_successful_getDemarche(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {
                        "nodes": [
                            {"number": 1, "groupeInstructeur": {"id": "GROUPE-1"}},
                            {"number": 2, "groupeInstructeur": {"id": "GROUPE-2"}},
                            {"number": 3, "groupeInstructeur": {"id": "GROUPE-1"}},
                        ]
                    },
                }
            }
        }

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        request_logs = self._request_log_records(cm.records)
        self.assertEqual(len(request_logs), 1)
        record = request_logs[0]
        self.assertEqual(record.outcome, "ok")
        self.assertEqual(record.root_field, "demarche")
        self.assertEqual(record.operation_name, "getDemarche")
        self.assertEqual(record.ds_results_count, 3)
        self.assertEqual(record.filtered_out_count, 1)
        self.assertEqual(record.ds_errors_count, 0)
        self.assertEqual(record.proxy_token_id, self.token.id)
        self.assertEqual(record.demarche_number, self.demarche.ds_number)
        self.assertTrue(record.request_id)
        self.assertIsInstance(record.elapsed_ms, int)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_counts_all_demarche_connections(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": self.demarche.ds_number,
                    "dossiers": {
                        "nodes": [
                            {"number": 1, "groupeInstructeur": {"id": "GROUPE-1"}},
                        ]
                    },
                    "pendingDeletedDossiers": {
                        "nodes": [
                            {"number": 2, "groupeInstructeur": {"id": "GROUPE-2"}},
                            {"number": 3, "groupeInstructeur": {"id": "GROUPE-1"}},
                        ]
                    },
                    "deletedDossiers": {
                        "nodes": [
                            {"number": 4, "groupeInstructeur": {"id": "GROUPE-2"}},
                        ]
                    },
                }
            }
        }

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        record = self._request_log_records(cm.records)[0]
        self.assertEqual(record.ds_results_count, 4)
        self.assertEqual(record.filtered_out_count, 2)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_on_authorized_getDossier(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "dossier": {
                    "number": 42,
                    "groupeInstructeur": {"id": "GROUPE-1"},
                    "demarche": {"number": self.demarche.ds_number},
                }
            }
        }

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(
                {
                    "query": "query getDossier { dossier { number } }",
                    "operationName": "getDossier",
                    "variables": {"dossierNumber": 42},
                }
            )
            _read_stream(response)

        record = self._request_log_records(cm.records)[0]
        self.assertEqual(record.outcome, "ok")
        self.assertEqual(record.root_field, "dossier")
        self.assertEqual(record.ds_results_count, 1)
        self.assertEqual(record.filtered_out_count, 0)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_on_filtered_getDossier(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "dossier": {
                    "number": 42,
                    "groupeInstructeur": {"id": "GROUPE-2"},
                    "demarche": {"number": self.demarche.ds_number},
                }
            }
        }

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(
                {
                    "query": "query getDossier { dossier { number } }",
                    "operationName": "getDossier",
                    "variables": {"dossierNumber": 42},
                }
            )
            _read_stream(response)

        record = self._request_log_records(cm.records)[0]
        self.assertEqual(record.outcome, "ok")
        self.assertEqual(record.ds_results_count, 1)
        self.assertEqual(record.filtered_out_count, 1)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_on_verbatim_forward(self, mock_post):
        upstream_errors = [
            {"message": "Field 'demaarche' doesn't exist on type 'Query'"},
        ]
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": None,
            "errors": upstream_errors,
        }

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        record = self._request_log_records(cm.records)[0]
        self.assertEqual(record.outcome, "verbatim_forward")
        self.assertEqual(record.ds_errors_count, len(upstream_errors))
        self.assertEqual(record.filtered_out_count, 0)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_on_scope_error(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "data": {
                "demarche": {
                    "number": 999,
                    "dossiers": {
                        "nodes": [
                            {"number": 1, "groupeInstructeur": {"id": "GROUPE-1"}},
                            {"number": 2, "groupeInstructeur": {"id": "GROUPE-2"}},
                        ]
                    },
                }
            }
        }

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(self._get_demarche_payload())
            _read_stream(response)

        record = self._request_log_records(cm.records)[0]
        self.assertEqual(record.outcome, "scope_error")
        self.assertEqual(record.ds_results_count, 2)
        self.assertEqual(record.filtered_out_count, record.ds_results_count)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_request_log_on_introspection_omits_dossier_counts(self, mock_post):
        introspection_payload = {"data": {"__schema": {"types": [{"name": "Query"}]}}}
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = introspection_payload

        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            response = self._post(
                {
                    "query": "query Whatever { __schema { types { name } } }",
                    "operationName": "Whatever",
                }
            )
            _read_stream(response)

        record = self._request_log_records(cm.records)[0]
        self.assertEqual(record.outcome, "ok")
        self.assertFalse(hasattr(record, "ds_results_count"))
        self.assertFalse(hasattr(record, "filtered_out_count"))

    def test_no_request_log_on_pre_ds_rejection(self):
        with self.assertLogs("gsl_ds_proxy.views", level="INFO") as cm:
            # assertLogs requires at least one record at the given level; emit
            # a sentinel so the context manager has something to capture.
            import logging as _logging

            _logging.getLogger("gsl_ds_proxy.views").info("sentinel")
            response = self._post({"query": "mutation { dossierAccepter { id } }"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._request_log_records(cm.records), [])


@override_settings(DS_API_TOKEN="test-ds-token", DS_API_URL="https://ds.test/graphql")
class GraphqlProxyTokenLockTest(TestCase):
    """One in-flight request per token, enforced by the Redis lock.

    The lock layer (`acquire_token_lock` / `release_token_lock`) is mocked here
    just like `requests.post` is, so the suite doesn't need a live Redis. The
    locks module itself is unit-tested in test_locks.py.
    """

    def setUp(self):
        self.demarche = DemarcheFactory(ds_number=123)
        self.token = ProxyTokenFactory(
            demarche=self.demarche,
            groupe_instructeur_ds_id="GROUPE-1",
        )
        self.url = "/ds-proxy/graphql/"
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token.plaintext_key}"}

    def _post(self, data, **extra_headers):
        headers = {**self.headers, **extra_headers}
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
            **headers,
        )

    def _get_demarche_payload(self):
        return {
            "query": "query getDemarche { demarche { number } }",
            "operationName": "getDemarche",
            "variables": {"demarcheNumber": self.demarche.ds_number},
        }

    def _mock_ds_success(self, mock_post):
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

    @patch("gsl_ds_proxy.views.release_token_lock")
    @patch("gsl_ds_proxy.views.acquire_token_lock", return_value=None)
    def test_concurrent_request_rejected_with_429(self, mock_acquire, mock_release):
        # acquire returns None => a request from this token is already in flight.
        response = self._post(self._get_demarche_payload())

        self.assertEqual(response.status_code, 429)
        body = json.loads(response.content)
        self.assertEqual(
            body["errors"][0]["message"],
            "Une seule requête à la fois est autorisée par token. "
            "Une requête est déjà en cours pour ce token, attendez sa fin "
            "avant d'en envoyer une autre.",
        )
        self.assertTrue(body["errors"][0]["extensions"]["requestId"])
        # No worker work happened and there is nothing to release.
        mock_release.assert_not_called()

    @patch("gsl_ds_proxy.views.requests.post")
    @patch("gsl_ds_proxy.views.release_token_lock")
    @patch("gsl_ds_proxy.views.acquire_token_lock")
    def test_lock_released_after_successful_request(
        self, mock_acquire, mock_release, mock_post
    ):
        fake_lock = MagicMock()
        mock_acquire.return_value = fake_lock
        self._mock_ds_success(mock_post)

        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 200)
        _read_stream(response)

        mock_release.assert_called_once_with(fake_lock, self.token.id)

    @patch("gsl_ds_proxy.views.requests.post")
    @patch("gsl_ds_proxy.views.release_token_lock")
    @patch("gsl_ds_proxy.views.acquire_token_lock")
    def test_lock_released_after_ds_error(self, mock_acquire, mock_release, mock_post):
        import requests as req

        fake_lock = MagicMock()
        mock_acquire.return_value = fake_lock
        mock_post.side_effect = req.exceptions.Timeout()

        response = self._post(self._get_demarche_payload())
        self.assertEqual(response.status_code, 200)
        # Drain the stream so the generator (and its finally) runs to the end.
        _read_stream(response)

        mock_release.assert_called_once_with(fake_lock, self.token.id)

    @patch("gsl_ds_proxy.views.requests.post")
    @patch("gsl_ds_proxy.views.release_token_lock")
    @patch("gsl_ds_proxy.views.acquire_token_lock")
    def test_distinct_tokens_acquire_independent_locks(
        self, mock_acquire, mock_release, mock_post
    ):
        # Each token gets its own lock keyed on its id, so they never block
        # one another even on the same démarche.
        other_token = ProxyTokenFactory(
            demarche=self.demarche,
            groupe_instructeur_ds_id="GROUPE-2",
        )
        mock_acquire.return_value = MagicMock()
        self._mock_ds_success(mock_post)

        self._read_ok(self._post(self._get_demarche_payload()))
        self._read_ok(
            self._post(
                self._get_demarche_payload(),
                HTTP_AUTHORIZATION=f"Bearer {other_token.plaintext_key}",
            )
        )

        acquired_token_ids = [call.args[0] for call in mock_acquire.call_args_list]
        self.assertEqual(acquired_token_ids, [self.token.id, other_token.id])

    def _read_ok(self, response):
        self.assertEqual(response.status_code, 200)
        _read_stream(response)

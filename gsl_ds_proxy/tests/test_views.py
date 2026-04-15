import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from gsl_demarches_simplifiees.tests.factories import ProfileFactory
from gsl_ds_proxy.tests.factories import ProxyTokenFactory


@override_settings(DS_API_TOKEN="test-ds-token", DS_API_URL="https://ds.test/graphql")
class GraphqlProxyViewTest(TestCase):
    def setUp(self):
        self.profile = ProfileFactory(ds_id="inst-a")
        self.token = ProxyTokenFactory()
        self.token.instructeurs.add(self.profile)
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

    def test_missing_auth_header(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"query": "{ demarche { title } }"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_token(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"query": "{ demarche { title } }"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid-token",
        )
        self.assertEqual(response.status_code, 401)

    def test_inactive_token(self):
        self.token.is_active = False
        self.token.save()
        response = self._post({"query": "{ demarche { title } }"})
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
                    }
                }
            }
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = ds_response_data

        response = self._post(
            {
                "query": "query getDemarche { demarche { dossiers { nodes { number } } } }",
                "variables": {"demarcheNumber": 123},
            }
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
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

        response = self._post({"query": "{ demarche { title } }"})
        self.assertEqual(response.status_code, 502)

    @patch("gsl_ds_proxy.views.requests.post")
    def test_ds_http_error(self, mock_post):
        import requests as req

        mock_post.return_value.status_code = 500
        mock_post.return_value.raise_for_status.side_effect = req.exceptions.HTTPError()

        response = self._post({"query": "{ demarche { title } }"})
        self.assertEqual(response.status_code, 502)

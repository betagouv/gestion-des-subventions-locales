from django.test import TestCase

from gsl_ds_proxy.filters import filter_response


def _make_dossier(number, groupe_id):
    return {
        "number": number,
        "groupeInstructeur": {"id": groupe_id} if groupe_id is not None else None,
    }


class FilterResponseDemarcheTest(TestCase):
    def _make_demarche_response(self, dossiers):
        return {
            "data": {
                "demarche": {
                    "dossiers": {
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": "abc",
                        },
                        "nodes": dossiers,
                    }
                }
            }
        }

    def test_filters_unauthorized_dossiers(self):
        response = self._make_demarche_response(
            [
                _make_dossier(1, "GROUPE-A"),
                _make_dossier(2, "GROUPE-B"),
                _make_dossier(3, "GROUPE-A"),
            ]
        )
        result = filter_response(response, "GROUPE-A")
        nodes = result["data"]["demarche"]["dossiers"]["nodes"]
        self.assertEqual([d["number"] for d in nodes], [1, 3])

    def test_preserves_page_info(self):
        response = self._make_demarche_response(
            [
                _make_dossier(1, "GROUPE-B"),
            ]
        )
        result = filter_response(response, "GROUPE-A")
        page_info = result["data"]["demarche"]["dossiers"]["pageInfo"]
        self.assertEqual(page_info["endCursor"], "abc")

    def test_empty_nodes(self):
        response = self._make_demarche_response([])
        result = filter_response(response, "GROUPE-A")
        self.assertEqual(result["data"]["demarche"]["dossiers"]["nodes"], [])

    def test_does_not_mutate_original(self):
        response = self._make_demarche_response(
            [
                _make_dossier(1, "GROUPE-A"),
                _make_dossier(2, "GROUPE-B"),
            ]
        )
        filter_response(response, "GROUPE-A")
        self.assertEqual(len(response["data"]["demarche"]["dossiers"]["nodes"]), 2)

    def test_dossier_without_groupe_instructeur_is_filtered_out(self):
        response = self._make_demarche_response(
            [
                {"number": 1, "groupeInstructeur": {}},
                {"number": 2},
            ]
        )
        result = filter_response(response, "GROUPE-A")
        self.assertEqual(result["data"]["demarche"]["dossiers"]["nodes"], [])

    def test_dossier_with_only_instructeurs_field_is_filtered_out(self):
        """Selection is strictly by groupe; legacy `instructeurs` field is ignored."""
        response = self._make_demarche_response(
            [
                {
                    "number": 1,
                    "instructeurs": [{"id": "inst-a", "email": "a@t.fr"}],
                },
            ]
        )
        result = filter_response(response, "GROUPE-A")
        self.assertEqual(result["data"]["demarche"]["dossiers"]["nodes"], [])

    def test_null_node_is_filtered_out(self):
        response = self._make_demarche_response(
            [
                _make_dossier(1, "GROUPE-A"),
                None,
                _make_dossier(2, "GROUPE-A"),
            ]
        )
        result = filter_response(response, "GROUPE-A")
        nodes = result["data"]["demarche"]["dossiers"]["nodes"]
        self.assertEqual([d["number"] for d in nodes], [1, 2])

    def test_top_level_errors_kept_when_filtered_list_is_empty(self):
        response = self._make_demarche_response(
            [
                _make_dossier(1, "GROUPE-B"),
            ]
        )
        response["errors"] = [{"message": "Could not fetch dossier 42"}]
        result = filter_response(response, "GROUPE-A")
        self.assertEqual(result["errors"], [{"message": "Could not fetch dossier 42"}])


class FilterResponseDeletedDossiersTest(TestCase):
    def _wrap(self, connection_field, dossiers):
        return {
            "data": {
                "demarche": {
                    connection_field: {
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": "abc",
                        },
                        "nodes": dossiers,
                    }
                }
            }
        }

    def test_pending_deleted_dossiers_filters_unauthorized(self):
        for connection_field in ("pendingDeletedDossiers", "deletedDossiers"):
            with self.subTest(connection_field=connection_field):
                response = self._wrap(
                    connection_field,
                    [
                        _make_dossier(1, "GROUPE-A"),
                        _make_dossier(2, "GROUPE-B"),
                        _make_dossier(3, "GROUPE-A"),
                    ],
                )
                result = filter_response(response, "GROUPE-A")
                nodes = result["data"]["demarche"][connection_field]["nodes"]
                self.assertEqual([d["number"] for d in nodes], [1, 3])

    def test_deleted_connections_preserve_page_info(self):
        for connection_field in ("pendingDeletedDossiers", "deletedDossiers"):
            with self.subTest(connection_field=connection_field):
                response = self._wrap(
                    connection_field,
                    [_make_dossier(1, "GROUPE-B")],
                )
                result = filter_response(response, "GROUPE-A")
                page_info = result["data"]["demarche"][connection_field]["pageInfo"]
                self.assertEqual(page_info["endCursor"], "abc")

    def test_deleted_connections_empty_nodes_pass_through(self):
        for connection_field in ("pendingDeletedDossiers", "deletedDossiers"):
            with self.subTest(connection_field=connection_field):
                response = self._wrap(connection_field, [])
                result = filter_response(response, "GROUPE-A")
                self.assertEqual(
                    result["data"]["demarche"][connection_field]["nodes"], []
                )

    def test_deleted_dossier_without_groupe_instructeur_is_dropped(self):
        for connection_field in ("pendingDeletedDossiers", "deletedDossiers"):
            with self.subTest(connection_field=connection_field):
                response = self._wrap(
                    connection_field,
                    [{"number": 1}, {"number": 2, "groupeInstructeur": {}}],
                )
                result = filter_response(response, "GROUPE-A")
                self.assertEqual(
                    result["data"]["demarche"][connection_field]["nodes"], []
                )

    def test_mixed_connections_filtered_independently(self):
        response = {
            "data": {
                "demarche": {
                    "dossiers": {
                        "pageInfo": {"hasNextPage": False, "endCursor": "a"},
                        "nodes": [
                            _make_dossier(1, "GROUPE-A"),
                            _make_dossier(2, "GROUPE-B"),
                        ],
                    },
                    "pendingDeletedDossiers": {
                        "pageInfo": {"hasNextPage": False, "endCursor": "b"},
                        "nodes": [
                            _make_dossier(10, "GROUPE-B"),
                            _make_dossier(11, "GROUPE-A"),
                        ],
                    },
                    "deletedDossiers": {
                        "pageInfo": {"hasNextPage": False, "endCursor": "c"},
                        "nodes": [
                            _make_dossier(20, "GROUPE-A"),
                            _make_dossier(21, "GROUPE-C"),
                        ],
                    },
                }
            }
        }
        result = filter_response(response, "GROUPE-A")
        demarche = result["data"]["demarche"]
        self.assertEqual([d["number"] for d in demarche["dossiers"]["nodes"]], [1])
        self.assertEqual(
            [d["number"] for d in demarche["pendingDeletedDossiers"]["nodes"]], [11]
        )
        self.assertEqual(
            [d["number"] for d in demarche["deletedDossiers"]["nodes"]], [20]
        )


class FilterResponseSingleDossierTest(TestCase):
    def test_authorized_dossier_passes_through(self):
        response = {
            "data": {
                "dossier": {
                    "number": 1,
                    "groupeInstructeur": {"id": "GROUPE-A"},
                }
            }
        }
        result = filter_response(response, "GROUPE-A")
        self.assertIsNotNone(result["data"]["dossier"])

    def test_unauthorized_dossier_returns_null_with_error(self):
        response = {
            "data": {
                "dossier": {
                    "number": 1,
                    "groupeInstructeur": {"id": "GROUPE-B"},
                }
            }
        }
        result = filter_response(response, "GROUPE-A")
        self.assertIsNone(result["data"]["dossier"])
        self.assertEqual(len(result["errors"]), 1)

    def test_dossier_without_groupe_instructeur_is_filtered_out(self):
        response = {
            "data": {
                "dossier": {
                    "number": 1,
                    "instructeurs": [{"id": "inst-a", "email": "a@t.fr"}],
                }
            }
        }
        result = filter_response(response, "GROUPE-A")
        self.assertIsNone(result["data"]["dossier"])


class FilterResponsePassthroughTest(TestCase):
    def test_no_data_passes_through(self):
        response = {"errors": [{"message": "some error"}]}
        result = filter_response(response, "GROUPE-A")
        self.assertEqual(result, response)

    def test_demarche_without_dossiers_passes_through(self):
        response = {"data": {"demarche": {"title": "Test"}}}
        result = filter_response(response, "GROUPE-A")
        self.assertEqual(result["data"]["demarche"]["title"], "Test")

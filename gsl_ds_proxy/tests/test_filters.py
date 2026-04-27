from django.test import TestCase

from gsl_ds_proxy.filters import filter_response


class FilterResponseDemarcheTest(TestCase):
    def _make_dossier(self, number, instructeur_ids):
        return {
            "number": number,
            "groupeInstructeur": {
                "instructeurs": [
                    {"id": iid, "email": f"{iid}@test.fr"} for iid in instructeur_ids
                ]
            },
            "instructeurs": [],
        }

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
                self._make_dossier(1, ["inst-a", "inst-b"]),
                self._make_dossier(2, ["inst-c"]),
                self._make_dossier(3, ["inst-a"]),
            ]
        )
        result = filter_response(response, {"inst-a"})
        nodes = result["data"]["demarche"]["dossiers"]["nodes"]
        self.assertEqual([d["number"] for d in nodes], [1, 3])

    def test_preserves_page_info(self):
        response = self._make_demarche_response(
            [
                self._make_dossier(1, ["inst-c"]),
            ]
        )
        result = filter_response(response, {"inst-a"})
        page_info = result["data"]["demarche"]["dossiers"]["pageInfo"]
        self.assertEqual(page_info["endCursor"], "abc")

    def test_empty_nodes(self):
        response = self._make_demarche_response([])
        result = filter_response(response, {"inst-a"})
        self.assertEqual(result["data"]["demarche"]["dossiers"]["nodes"], [])

    def test_does_not_mutate_original(self):
        response = self._make_demarche_response(
            [
                self._make_dossier(1, ["inst-a"]),
                self._make_dossier(2, ["inst-b"]),
            ]
        )
        filter_response(response, {"inst-a"})
        self.assertEqual(len(response["data"]["demarche"]["dossiers"]["nodes"]), 2)

    def test_dossier_without_instructeur_data_is_filtered_out(self):
        response = self._make_demarche_response(
            [
                {"number": 1, "groupeInstructeur": {}},
                {"number": 2},
            ]
        )
        result = filter_response(response, {"inst-a"})
        self.assertEqual(result["data"]["demarche"]["dossiers"]["nodes"], [])

    def test_null_node_is_filtered_out(self):
        response = self._make_demarche_response(
            [
                self._make_dossier(1, ["inst-a"]),
                None,
                self._make_dossier(2, ["inst-a"]),
            ]
        )
        result = filter_response(response, {"inst-a"})
        nodes = result["data"]["demarche"]["dossiers"]["nodes"]
        self.assertEqual([d["number"] for d in nodes], [1, 2])

    def test_top_level_errors_dropped_when_dossiers_present(self):
        response = self._make_demarche_response(
            [
                self._make_dossier(1, ["inst-a"]),
                None,
            ]
        )
        response["errors"] = [{"message": "Could not fetch dossier 42"}]
        result = filter_response(response, {"inst-a"})
        self.assertNotIn("errors", result)

    def test_top_level_errors_kept_when_filtered_list_is_empty(self):
        response = self._make_demarche_response(
            [
                self._make_dossier(1, ["inst-c"]),
            ]
        )
        response["errors"] = [{"message": "Could not fetch dossier 42"}]
        result = filter_response(response, {"inst-a"})
        self.assertEqual(result["errors"], [{"message": "Could not fetch dossier 42"}])


class FilterResponseSingleDossierTest(TestCase):
    def test_authorized_dossier_passes_through(self):
        response = {
            "data": {
                "dossier": {
                    "number": 1,
                    "groupeInstructeur": {
                        "instructeurs": [{"id": "inst-a", "email": "a@t.fr"}]
                    },
                    "instructeurs": [],
                }
            }
        }
        result = filter_response(response, {"inst-a"})
        self.assertIsNotNone(result["data"]["dossier"])

    def test_unauthorized_dossier_returns_null_with_error(self):
        response = {
            "data": {
                "dossier": {
                    "number": 1,
                    "groupeInstructeur": {
                        "instructeurs": [{"id": "inst-b", "email": "b@t.fr"}]
                    },
                    "instructeurs": [],
                }
            }
        }
        result = filter_response(response, {"inst-a"})
        self.assertIsNone(result["data"]["dossier"])
        self.assertEqual(len(result["errors"]), 1)


class FilterResponsePassthroughTest(TestCase):
    def test_no_data_passes_through(self):
        response = {"errors": [{"message": "some error"}]}
        result = filter_response(response, {"inst-a"})
        self.assertEqual(result, response)

    def test_demarche_without_dossiers_passes_through(self):
        response = {"data": {"demarche": {"title": "Test"}}}
        result = filter_response(response, {"inst-a"})
        self.assertEqual(result["data"]["demarche"]["title"], "Test")

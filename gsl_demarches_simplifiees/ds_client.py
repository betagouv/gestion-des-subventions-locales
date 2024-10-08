from pathlib import Path

import requests
from django.conf import settings


class DsClient:
    def __init__(self):
        self.token = settings.DS_API_TOKEN
        self.url = settings.DS_API_URL
        with open(
            Path(__file__).resolve().parent / "graphql" / "ds_queries.gql"
        ) as query_file:
            self.query = query_file.read()

    def launch_graphql_query(self, operation_name, variables=None):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        data = {"query": self.query, "operationName": operation_name}
        if variables:
            data["variables"] = variables

        response = requests.post(self.url, json=data, headers=headers)
        if response.status_code == 200:
            results = response.json()
            if "errors" in results.keys():
                print(results["errors"])  # @todo loguer ça bien
                raise Exception(f"Query failed to run: {results['errors']}")
            return results
        else:
            raise Exception(
                f"HTTP Error while running query. Status code: {response.status_code}. "
                f"Error: {response.text}"
            )

    def get_demarche(self, demarche_number):
        """
        Get info about one demarche, without its dossiers.
        Use it to get the list of instructeurs and the list of fields with their ids.
        :param demarche_number: integer
        :return: json string
        """
        variables = {
            "demarcheNumber": demarche_number,
            "includeDossiers": False,
            "includeGroupeInstructeurs": True,
            "includeRevision": True,  # to list custom fields with their ids
        }
        return self.launch_graphql_query("getDemarche", variables=variables)

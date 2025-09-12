from collections.abc import Iterator
from logging import getLogger
from pathlib import Path

import requests
from django.conf import settings

from gsl_demarches_simplifiees.exceptions import DsServiceException

logger = getLogger(__name__)


class DsClientBase:
    filename = ""

    def __init__(self):
        self.token = settings.DS_API_TOKEN
        self.url = settings.DS_API_URL
        with open(
            Path(__file__).resolve().parent / "graphql" / self.filename
        ) as query_file:
            self.query = query_file.read()

    def launch_graphql_query(self, operation_name, variables=None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        data = {"query": self.query, "operationName": operation_name}
        if variables:
            data["variables"] = variables
        try:
            response = requests.post(self.url, json=data, headers=headers)

        except requests.exceptions.ConnectionError as e:
            logger.warning("DS connection error", extra={"erreur": e})
            raise Exception("Erreur de connexion à Démarches Simplifiées")

        if response.status_code == 200:
            results = response.json()
            if "errors" in results.keys() and results.get("data", None) is None:
                logger.error(
                    "DS request error", extra={**variables, "error": results["errors"]}
                )
                raise DsServiceException
            return results
        else:
            if response.status_code == 403:
                logger.critical(
                    "DS forbidden access : token problem ?",
                    extra={"error": response.text},
                )
            else:
                logger.error(
                    "DS request error",
                    extra={"status_code": response.status_code, "error": response.text},
                )
            raise Exception(
                f"HTTP Error while running query. Status code: {response.status_code}. "
                f"Error: {response.text}"
            )


class DsClient(DsClientBase):
    filename = "ds_queries.gql"

    def get_demarche(self, demarche_number) -> dict:
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

    def get_demarche_dossiers(self, demarche_number) -> Iterator[dict]:
        """
        Get all dossiers from one given demarche
        :param demarche_number:
        :return: iterator on all available dossiers of demarche
        """
        variables = {
            "demarcheNumber": demarche_number,
            "includeDossiers": True,
        }
        result = self.launch_graphql_query("getDemarche", variables=variables)
        yield from result["data"]["demarche"]["dossiers"]["nodes"]
        has_next_page = result["data"]["demarche"]["dossiers"]["pageInfo"][
            "hasNextPage"
        ]
        while has_next_page:
            end_cursor = result["data"]["demarche"]["dossiers"]["pageInfo"]["endCursor"]
            has_next_page = result["data"]["demarche"]["dossiers"]["pageInfo"][
                "hasNextPage"
            ]
            variables["after"] = end_cursor
            result = self.launch_graphql_query("getDemarche", variables=variables)
            yield from result["data"]["demarche"]["dossiers"]["nodes"]

    def get_one_dossier(self, dossier_number) -> dict:
        variables = {
            "dossierNumber": dossier_number,
        }
        result = self.launch_graphql_query("getDossier", variables)
        return result["data"]["dossier"]


class DsMutator(DsClientBase):
    filename = "ds_mutations.gql"

    def dossier_modifier_annotation_checkbox(
        self,
        dossier_id: str,
        instructeur_id: str,
        field_id: str,
        value: bool,
        include_annotations=False,
    ):
        variables = {
            "input": {
                "clientMutationId": settings.DS_CLIENT_ID,
                "annotationId": field_id,
                "dossierId": dossier_id,
                "instructeurId": instructeur_id,
                "value": value,
            },
            "includeAnnotations": include_annotations,
        }
        return self.launch_graphql_query(
            "modifierAnnotationCheckbox", variables=variables
        )

    def dossier_modifier_annotation_decimal(
        self,
        dossier_id: str,
        instructeur_id: str,
        field_id: str,
        value: float,
        include_annotations=False,
    ):
        variables = {
            "input": {
                "clientMutationId": settings.DS_CLIENT_ID,
                "annotationId": field_id,
                "dossierId": dossier_id,
                "instructeurId": instructeur_id,
                "value": value,
            },
            "includeAnnotations": include_annotations,
        }
        return self.launch_graphql_query(
            "modifierAnnotationDecimalNumber", variables=variables
        )

    def dossier_repasser_en_instruction(
        self, dossier_id, instructeur_id, disable_notification=False
    ):
        variables = {
            "input": {
                "clientMutationId": settings.DS_CLIENT_ID,
                "disableNotification": disable_notification,
                "dossierId": dossier_id,
                "instructeurId": instructeur_id,
            }
        }
        return self.launch_graphql_query(
            "dossierRepasserEnInstruction", variables=variables
        )

    def dossier_passer_en_instruction(
        self, dossier_id, instructeur_id, disable_notification=False
    ):
        variables = {
            "input": {
                "clientMutationId": settings.DS_CLIENT_ID,
                "disableNotification": disable_notification,
                "dossierId": dossier_id,
                "instructeurId": instructeur_id,
            }
        }
        return self.launch_graphql_query(
            "dossierPasserEnInstruction", variables=variables
        )

    def mutate_with_justificatif_and_motivation(
        self,
        action,
        dossier_id,
        instructeur_id,
        motivation="",
        justificatif_id=None,
        disable_notification=False,
    ):
        variables = {
            "input": {
                "clientMutationId": settings.DS_CLIENT_ID,
                "disableNotification": disable_notification,
                "dossierId": dossier_id,
                "instructeurId": instructeur_id,
            }
        }
        if motivation:
            variables["input"]["motivation"] = motivation

        if justificatif_id:
            variables["input"]["justificatif"] = justificatif_id
        return self.launch_graphql_query(action, variables=variables)

    def dossier_accepter(self, *args, **kwargs):
        return self.mutate_with_justificatif_and_motivation(
            "dossierAccepter", *args, **kwargs
        )

    def dossier_classer_sans_suite(self, *args, **kwargs):
        return self.mutate_with_justificatif_and_motivation(
            "dossierClasserSansSuite", *args, **kwargs
        )

    def dossier_refuser(self, *args, **kwargs):
        return self.mutate_with_justificatif_and_motivation(
            "dossierRefuser", *args, **kwargs
        )

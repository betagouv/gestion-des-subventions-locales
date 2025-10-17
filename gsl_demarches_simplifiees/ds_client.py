import base64
import hashlib
import json
from collections.abc import Iterator
from logging import getLogger
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from gsl_demarches_simplifiees.exceptions import DsConnectionError, DsServiceException
from gsl_demarches_simplifiees.models import Dossier

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
            raise DsConnectionError()

        if response.status_code == 200:
            results = response.json()
            if "errors" in results.keys():
                for error in results["errors"]:
                    logger.error(f"DS request error : {error['message']}")
                if results.get("data", None) is None:
                    raise DsServiceException
            return results
        else:
            if response.status_code == 403:
                logger.critical(
                    "DS forbidden access : token problem ?",
                    extra={"error": response.text},
                )
                raise DsConnectionError()
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
        # TODO : We should check response to know if the dossier is in instruction after that
        # for the moment, if the dossier is in construction, it silently fails without any error
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

    def _mutate_with_justificatif_and_motivation(
        self,
        action: str,
        dossier_ds_id: str,
        instructeur_id: str,
        motivation: str = "",
        justificatif_id: str | None = None,
        disable_notification: bool = False,
    ):
        variables = {
            "input": {
                "clientMutationId": settings.DS_CLIENT_ID,
                "disableNotification": disable_notification,
                "dossierId": dossier_ds_id,
                "instructeurId": instructeur_id,
            }
        }
        if motivation:
            variables["input"]["motivation"] = motivation

        if justificatif_id:
            variables["input"]["justificatif"] = justificatif_id
        return self.launch_graphql_query(action, variables=variables)

    def _upload_attachment(self, dossier_ds_id: str, file: UploadedFile) -> str:
        """
        Upload a file to Démarches Simplifiées using GraphQL mutation.

        :param file: UploadedFile instance. It must be a PDF file.
        :param dossier_id: ID of the dossier to attach the file to.
        :return: signedBlobId of the uploaded file.
        """
        res = self.launch_graphql_query(
            "createDirectUpload",
            {
                "input": {
                    "dossierId": dossier_ds_id,
                    "filename": file.name,
                    "byteSize": file.size,
                    "checksum": base64.b64encode(
                        hashlib.md5(file.read()).digest()
                    ).decode(),
                    "contentType": "application/pdf",
                }
            },
        )
        upload_url = res["data"]["createDirectUpload"]["directUpload"]["url"]
        credential_headers = json.loads(
            res["data"]["createDirectUpload"]["directUpload"]["headers"]
        )
        blob_id = res["data"]["createDirectUpload"]["directUpload"]["signedBlobId"]
        try:
            file.seek(0)
            res = requests.put(upload_url, data=file.read(), headers=credential_headers)
            if not 200 <= res.status_code < 300:
                raise DsServiceException(f"Error uploading file: {res}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            raise DsConnectionError()

        return blob_id

    def dossier_accepter(
        self,
        dossier: Dossier,
        instructeur_id: str,
        motivation: str = "",
        disable_notification: bool = False,
        document: UploadedFile = None,
    ):
        justificatif_id = (
            self._upload_attachment(dossier.ds_id, document)
            if document is not None
            else None
        )
        return self._mutate_with_justificatif_and_motivation(
            "dossierAccepter",
            dossier_ds_id=dossier.ds_id,
            instructeur_id=instructeur_id,
            motivation=motivation,
            disable_notification=disable_notification,
            justificatif_id=justificatif_id,
        )

    def dossier_classer_sans_suite(
        self,
        dossier_id: str,
        instructeur_id: str,
        motivation: str = "",
        document: UploadedFile = None,
    ):
        if document is not None:
            justificatif_id = self._upload_attachment(dossier_id, document)
        else:
            justificatif_id = None
        return self._mutate_with_justificatif_and_motivation(
            "dossierClasserSansSuite",
            dossier_id,
            instructeur_id,
            motivation,
            justificatif_id,
        )

    def dossier_refuser(
        self,
        dossier: Dossier,
        instructeur_id: str,
        motivation: str = "",
        document: UploadedFile = None,
    ):
        if document is not None:
            justificatif_id = self._upload_attachment(dossier.ds_id, document)
        else:
            justificatif_id = None
        return self._mutate_with_justificatif_and_motivation(
            "dossierRefuser", dossier.ds_id, instructeur_id, motivation, justificatif_id
        )

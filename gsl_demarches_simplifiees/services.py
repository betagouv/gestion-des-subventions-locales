from datetime import datetime
from logging import getLogger
from typing import List, Literal

from django.core.exceptions import FieldDoesNotExist
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.utils import timezone

from gsl.historique.models import ProjetAction
from gsl.projet.constants import (
    DOTATION_DSIL,
    DS_TRAITEMENT_EVENT_ACCEPTE,
    DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
    DS_TRAITEMENT_EVENT_REFUSE,
    DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION,
    POSSIBLE_DOTATIONS,
)
from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.exceptions import (
    DsServiceException,
    FieldError,
    InstructeurUnknown,
    UserRightsError,
)
from gsl_demarches_simplifiees.models import Dossier, FieldMapping
from gsl_demarches_simplifiees.utils import most_recent_traitement

logger = getLogger(__name__)


class DsService:
    MUTATION_KEYS = {
        "accept": "dossierAccepter",
        "dismiss": "dossierClasserSansSuite",
        "refuser": "dossierRefuser",
        "annotations": "dossierModifierAnnotations",
        "passer_en_instruction": "dossierPasserEnInstruction",
        "repasser_en_instruction": "dossierRepasserEnInstruction",
    }

    MUTATION_TYPES = Literal[
        "accept",
        "dismiss",
        "refuser",
        "annotations",
        "passer_en_instruction",
        "repasser_en_instruction",
    ]

    # Événement DN (`traitements[].event`) attendu pour le traitement créé
    # par chaque mutation, utilisé pour fiabiliser `most_recent_traitement`.
    MUTATION_EXPECTED_EVENTS = {
        "accept": DS_TRAITEMENT_EVENT_ACCEPTE,
        "dismiss": DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
        "refuser": DS_TRAITEMENT_EVENT_REFUSE,
        "passer_en_instruction": DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
        "repasser_en_instruction": DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION,
    }

    def __init__(self):
        self.mutator = DsMutator()

    # Status

    def passer_en_instruction(self, dossier: Dossier, user: Collegue) -> None:
        from gsl_demarches_simplifiees.importer.dossier import (
            refresh_dossier_from_saved_data,
        )

        mutation = "passer_en_instruction"

        results = self.mutator.dossier_passer_en_instruction(dossier.ds_id, user.ds_id)
        self._check_results(results, dossier, user, mutation)

        dossier_data = self._get_dossier_data(results, mutation)
        dossier.update_data(dossier_data)
        self._create_projet_action_for_mutation(
            dossier,
            user,
            mutation,
            ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
            dossier_data,
        )

        refresh_dossier_from_saved_data(dossier)

    def repasser_en_instruction(self, dossier: Dossier, user: Collegue) -> None:
        from gsl_demarches_simplifiees.importer.dossier import (
            refresh_dossier_from_saved_data,
        )

        mutation = "repasser_en_instruction"

        results = self.mutator.dossier_repasser_en_instruction(
            dossier.ds_id, user.ds_id
        )
        self._check_results(results, dossier, user, mutation)

        dossier_data = self._get_dossier_data(results, mutation)
        dossier.update_data(dossier_data)
        self._create_projet_action_for_mutation(
            dossier,
            user,
            mutation,
            ProjetAction.TYPE_RETOUR_EN_INSTRUCTION,
            dossier_data,
        )

        refresh_dossier_from_saved_data(dossier)

    def accept_in_ds(
        self,
        dossier: Dossier,
        user: Collegue,
        document: UploadedFile,
        motivation: str = "",
    ) -> None:
        from gsl_demarches_simplifiees.importer.dossier import (
            refresh_dossier_from_saved_data,
        )

        mutation = "accept"
        instructeur_id = self._get_instructeur_id(user)
        results = self.mutator.dossier_accepter(
            dossier.ds_id, instructeur_id, motivation=motivation, document=document
        )
        self._check_results(results, dossier, user, mutation, value=motivation)

        dossier_data = self._get_dossier_data(results, mutation)
        dossier.update_data(dossier_data)
        self._create_projet_action_for_mutation(
            dossier,
            user,
            mutation,
            ProjetAction.TYPE_NOTIFIED,
            dossier_data,
            document=document,
            motivation=motivation,
        )
        refresh_dossier_from_saved_data(dossier)

    def dismiss_in_ds(
        self,
        dossier: Dossier,
        user: Collegue,
        motivation: str,
        document: UploadedFile | None = None,
    ) -> None:
        from gsl_demarches_simplifiees.importer.dossier import (
            refresh_dossier_from_saved_data,
        )

        mutation = "dismiss"
        instructeur_id = self._get_instructeur_id(user)
        results = self.mutator.dossier_classer_sans_suite(
            dossier.ds_id, instructeur_id, motivation, document=document
        )
        self._check_results(results, dossier, user, mutation, value=motivation)

        dossier_data = self._get_dossier_data(results, mutation)
        dossier.update_data(dossier_data)

        self._create_projet_action_for_mutation(
            dossier,
            user,
            mutation,
            ProjetAction.TYPE_NOTIFIED,
            dossier_data,
            document=document,
            motivation=motivation,
        )
        refresh_dossier_from_saved_data(dossier)

    def refuser_in_ds(
        self,
        dossier: Dossier,
        user: Collegue,
        motivation: str,
        document: UploadedFile | None = None,
    ) -> None:
        from gsl_demarches_simplifiees.importer.dossier import (
            refresh_dossier_from_saved_data,
        )

        mutation = "refuser"
        instructeur_id = self._get_instructeur_id(user)
        results = self.mutator.dossier_refuser(
            dossier, instructeur_id, motivation=motivation, document=document
        )
        self._check_results(results, dossier, user, mutation, value=motivation)

        dossier_data = self._get_dossier_data(results, mutation)
        dossier.update_data(dossier_data)

        self._create_projet_action_for_mutation(
            dossier,
            user,
            mutation,
            ProjetAction.TYPE_NOTIFIED,
            dossier_data,
            document=document,
            motivation=motivation,
        )
        refresh_dossier_from_saved_data(dossier)

    def _create_projet_action_for_mutation(
        self,
        dossier: Dossier,
        user: Collegue,
        mutation_type: MUTATION_TYPES,
        action_type: str,
        dossier_data: dict,
        document: UploadedFile | None = None,
        motivation: str = "",
    ) -> None:
        """Met à jour `dossier.ds_date_traitement` et crée le ProjetAction
        (source Turgot) correspondant à la mutation DN (notification,
        passage ou retour en instruction)."""
        from gsl.projet.models import Projet

        date_traitement = dossier_data.get("dateTraitement")
        if date_traitement:
            dossier.ds_date_traitement = datetime.fromisoformat(date_traitement)
            dossier.save()

        traitements = dossier_data.get("traitements") or []
        traitement = most_recent_traitement(
            traitements, self.MUTATION_EXPECTED_EVENTS[mutation_type]
        )
        traitement_id = traitement["id"] if traitement else None

        try:
            projet = dossier.projet
        except Projet.DoesNotExist:
            return

        created_at = (
            datetime.fromisoformat(traitement["dateTraitement"])
            if traitement and traitement.get("dateTraitement")
            else timezone.now()
        )

        action = ProjetAction(
            projet=projet,
            action_type=action_type,
            actor=user,
            source=ProjetAction.SOURCE_TURGOT,
            source_id=traitement_id or "",
            details=motivation,
            created_at=created_at,
        )
        if document:
            document.seek(0)
            action.document.save(document.name, document, save=False)
        action.save()

    def _get_dossier_data(self, results: dict, mutation_type: MUTATION_TYPES) -> dict:
        """Extrait le sous-objet `dossier` de la réponse d'une mutation DN
        (cf `ds_mutations.gql`), ou `{}` s'il est absent."""
        mutation_key = self.MUTATION_KEYS[mutation_type]
        return results.get("data", {}).get(mutation_key, {}).get("dossier") or {}

    # Annotations

    def update_ds_annotations_for_one_dotation(
        self,
        dossier: Dossier,
        user: Collegue,
        dotations_to_be_checked: list[POSSIBLE_DOTATIONS],
        annotations_dotation_to_update: POSSIBLE_DOTATIONS | None = None,
        assiette: float | None = None,
        montant: float | None = None,
        taux: float | None = None,
    ):
        if annotations_dotation_to_update is None:
            if assiette is not None or montant is not None or taux is not None:
                raise ValueError(
                    "annotations_dotation_to_update must be provided if assiette, montant or taux are provided"
                )

        annotations = [
            {
                "id": self._get_ds_field_id(dossier, "annotations_dotation"),
                "value": {"multipleDropDownList": dotations_to_be_checked},
            }
        ]

        if annotations_dotation_to_update:
            suffix = (
                "dsil" if annotations_dotation_to_update == DOTATION_DSIL else "detr"
            )

            if assiette is not None:
                annotations.append(
                    {
                        "id": self._get_ds_field_id(
                            dossier, f"annotations_assiette_{suffix}"
                        ),
                        "value": {"decimalNumber": assiette},
                    }
                )
            if montant is not None:
                annotations.append(
                    {
                        "id": self._get_ds_field_id(
                            dossier, f"annotations_montant_accorde_{suffix}"
                        ),
                        "value": {"decimalNumber": montant},
                    }
                )
            if taux is not None:
                annotations.append(
                    {
                        "id": self._get_ds_field_id(
                            dossier, f"annotations_taux_{suffix}"
                        ),
                        "value": {"decimalNumber": round(taux, 3)},
                    }
                )

        results = self.mutator.dossier_modifier_annotations(
            dossier.ds_id, user.ds_id, annotations
        )
        self._check_results(results, dossier, user, "annotations", value=annotations)
        self._update_updated_at_from_multiple_annotations(dossier, results)
        return results

    def update_annotations(
        self,
        dossier: Dossier,
        user: Collegue,
        annotations: dict[str, bool | str],
    ):
        ds_annotations = []
        for annotation_key, value in annotations.items():
            field = Dossier._meta.get_field(annotation_key)
            ds_value = (
                {"checkbox": bool(value)}
                if isinstance(field, models.BooleanField)
                else {"text": value}
            )
            ds_annotations.append(
                {
                    "id": self._get_ds_field_id(dossier, annotation_key),
                    "value": ds_value,
                }
            )
        results = self.mutator.dossier_modifier_annotations(
            dossier.ds_id, user.ds_id, ds_annotations
        )
        self._check_results(results, dossier, user, "annotations", value=ds_annotations)
        self._update_updated_at_from_multiple_annotations(dossier, results)
        return results

    # Private

    def _update_updated_at(self, dossier: Dossier, results: dict):
        updated_at = results.get("data", {}).get("updatedAt")
        if updated_at:
            dossier.ds_date_derniere_modification = updated_at
            dossier.save()

    def _update_updated_at_from_multiple_annotations(
        self, dossier: Dossier, results: dict
    ):
        most_recent_updated_at = None
        annotations = (
            results.get("data", {})
            .get("dossierModifierAnnotations", {})
            .get("annotations", [])
        )
        for annotation in annotations:
            updated_at = datetime.fromisoformat(annotation.get("updatedAt"))
            if updated_at and (
                most_recent_updated_at is None or updated_at > most_recent_updated_at
            ):
                most_recent_updated_at = updated_at

        if most_recent_updated_at:
            dossier.ds_date_derniere_modification = most_recent_updated_at
            dossier.save()

    def _get_instructeur_id(self, user: Collegue) -> str:
        instructeur_id = user.ds_id
        if bool(instructeur_id):
            return str(instructeur_id)

        raise InstructeurUnknown(extra={"user_id": user.id})

    def _get_ds_field_id(self, dossier: Dossier, field: str) -> str:
        try:
            ds_field = FieldMapping.actives.get(
                demarche=dossier.ds_demarche_id, django_field=field
            )
            return ds_field.ds_field_id

        except FieldMapping.DoesNotExist:
            field_name = field
            try:
                field_name = Dossier._meta.get_field(field).verbose_name
            except FieldDoesNotExist:
                pass

            raise FieldError(
                f'Le champ "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche_number}.',
                extra={
                    "field_name": field_name,
                    "demarche_ds_number": dossier.ds_demarche_number,
                    "dossier_ds_number": dossier.ds_number,
                },
            )

    def _check_results(
        self,
        results: dict,
        dossier: Dossier,
        user: Collegue,
        mutation_type: MUTATION_TYPES,
        field: str | None = None,
        value: float | bool | str | None = None,
    ) -> None:
        mutation_key = self.MUTATION_KEYS[mutation_type]
        data = results.get("data", None)

        if data is None or mutation_key in data and data.get(mutation_key) is None:
            if "errors" not in results.keys():
                return

            errors = results["errors"]
            messages = [error["message"] for error in errors]
            message = self._transform_message(messages)

            raise DsServiceException(
                message,
                log_message="Error in DN mutation",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "user_id": user.id,
                    "mutation_key": mutation_key,
                    "field": field,
                    "value": value,
                    "error": messages,
                },
            )

        mutation_data = data.get(mutation_key)
        if mutation_data is None or "errors" not in mutation_data:
            return

        errors = mutation_data["errors"]
        if not bool(errors):
            return

        messages = [error["message"] for error in errors]
        if "L’instructeur n’a pas les droits d’accès à ce dossier" in messages:
            raise UserRightsError(
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "user_id": user.id,
                }
            )

        message = self._transform_message(messages)
        raise DsServiceException(
            message,
            log_message="Error in DN mutation",
            extra={
                "dossier_ds_number": dossier.ds_number,
                "user_id": user.id,
                "mutation_key": mutation_key,
                "field": field,
                "value": value,
                "error": messages,
            },
        )

    def _transform_message(self, messages: List[str]) -> str:
        new_messages = []
        for message in messages:
            if message == "Le dossier est déjà en\xa0construction":
                new_messages.append(
                    "Le dossier est en construction sur Démarche Numérique."
                )
            elif message == "An object of type Dossier was hidden due to permissions":
                new_messages.append("Vous n'avez pas accès à ce dossier.")
            else:
                new_messages.append(message)

        return ". ".join(new_messages)

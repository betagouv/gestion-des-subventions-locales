import logging
from typing import Iterable

from django.contrib import messages
from django.utils import timezone

from gsl_core.models import Departement
from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import Demarche, Dossier, Profile
from gsl_projet.services.projet_services import ProjetService

logger = logging.getLogger(__name__)


def save_demarche_dossiers_from_ds(demarche_number, using_updated_since: bool = True):
    new_updated_since = timezone.now()

    demarche = Demarche.objects.get(ds_number=demarche_number)
    client = DsClient()
    updated_since = demarche.updated_since if using_updated_since else None
    demarche_dossiers = client.get_demarche_dossiers(
        demarche_number, updated_since=updated_since
    )
    active_departement_insee_codes = _get_active_departement_insee_codes()
    dossiers_count = 0
    for dossier_data in demarche_dossiers:
        dossiers_count += 1

        if dossier_data is None:
            logger.info(
                "Dossier data is empty",
                extra={
                    "demarche_ds_number": demarche_number,
                    "i": dossiers_count,
                },
            )
            continue

        _create_or_update_dossier_from_ds_data(
            dossier_data, active_departement_insee_codes, demarche, dossiers_count
        )

    logger.info(
        "Demarche dossiers has been updated from DN",
        extra={
            "demarche_ds_number": demarche_number,
            "dossiers_count": dossiers_count,
        },
    )

    demarche.updated_since = new_updated_since
    demarche.save()


def save_one_dossier_from_ds(
    dossier: Dossier,
    client: DsClient | None = None,
    refresh_only_if_dossier_has_been_updated: bool = True,
):
    client = client or DsClient()
    dossier_data = client.get_one_dossier(dossier.ds_number)
    has_dossier_been_updated = _save_dossier_data_and_refresh_dossier_and_projet_and_co(
        dossier,
        dossier_data,
        refresh_only_if_dossier_has_been_updated=refresh_only_if_dossier_has_been_updated,
    )

    if has_dossier_been_updated:
        return (
            messages.SUCCESS,
            "Le dossier a bien été mis à jour depuis Démarche Numérique.",
        )
    return (
        messages.WARNING,
        (
            "Le dossier était déjà à jour sur Turgot, nous ne l’avons pas "
            "remis à jour depuis Démarche Numérique."
        ),
    )


def create_or_update_dossier_from_ds_data(ds_number: str):
    client = DsClient()
    dossier_data = client.get_one_dossier(ds_number)
    active_departement_insee_codes = _get_active_departement_insee_codes()
    return _create_or_update_dossier_from_ds_data(
        dossier_data, active_departement_insee_codes
    )


def refresh_dossier_from_saved_data(dossier: Dossier):
    dossier_converter = DossierConverter(dossier.raw_ds_data, dossier)
    dossier_converter.fill_unmapped_fields()
    dossier_converter.convert_all_fields()
    try:
        dossier.save()
    except Exception as e:
        logger.error(str(e), extra={"dossier_id": dossier.id})
        raise e

    ProjetService.create_or_update_projet_and_co_from_dossier(dossier.ds_number)


def refresh_dossier_instructeurs(dossier_data, dossier: Dossier):
    """
    Refreshes the instructeurs associated with a dossier based on data from Démarche Numérique.

    Assume ds_instructeur has been prefetch_related on dossier
    Noop if no changes, check only IDs does not check emails.
    """
    if "groupeInstructeur" not in dossier_data:
        # Should not happen except in tests
        return
    instructeurs_data = dossier_data["groupeInstructeur"]["instructeurs"]

    # Remove instructeurs that are not in the new data
    for profile in dossier.ds_instructeurs.all():
        if profile.ds_id not in (i["id"] for i in instructeurs_data):
            dossier.ds_instructeurs.remove(profile)

    # Add instructeurs that are not already in the dossier
    dossier_instructeurs_ids = [p.ds_id for p in dossier.ds_instructeurs.all()]
    for instructeur_data in instructeurs_data:
        if instructeur_data["id"] not in dossier_instructeurs_ids:
            instructeur, _ = Profile.objects.get_or_create(
                ds_id=instructeur_data["id"], ds_email=instructeur_data["email"]
            )
            dossier.ds_instructeurs.add(instructeur)


### Private methods


def _save_dossier_data_and_refresh_dossier_and_projet_and_co(
    dossier: Dossier,
    dossier_data: dict,
    async_refresh: bool = False,
    refresh_only_if_dossier_has_been_updated: bool = True,
):
    if refresh_only_if_dossier_has_been_updated:
        must_refresh_dossier = _has_dossier_been_updated_on_ds(dossier, dossier_data)
    else:
        must_refresh_dossier = True

    refresh_dossier_instructeurs(dossier_data, dossier)
    dossier.raw_ds_data = dossier_data
    dossier.save()

    if must_refresh_dossier:
        if async_refresh:
            from gsl_demarches_simplifiees.tasks import (
                task_refresh_dossier_from_saved_data,
            )

            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)
        else:
            refresh_dossier_from_saved_data(dossier)

    return must_refresh_dossier


def _has_dossier_been_updated_on_ds(dossier: Dossier, dossier_data: dict) -> bool:
    date_modif_ds = dossier_data.get("dateDerniereModification", None)

    if not date_modif_ds:
        raise DsServiceException(
            "Une erreur est survenue lors de la mise à jour du dossier.",
            level=logging.ERROR,
            log_message="Unset date_modif_ds is not a normal situation.",
            extra={
                "dossier_ds_number": dossier.ds_number,
            },
        )

    if dossier.ds_date_derniere_modification is None:
        return True  # New dossier on Turgot

    date_modif_ds = timezone.datetime.fromisoformat(date_modif_ds)
    return date_modif_ds > dossier.ds_date_derniere_modification


def _get_active_departement_insee_codes():
    return Departement.objects.filter(active=True).values_list("insee_code", flat=True)


def _is_dossier_in_active_departement(
    raw_data: dict, departements_actifs: Iterable[str]
) -> bool:
    champs = raw_data.get("champs", [])

    for champ in champs:
        if champ.get("label") == "Département ou collectivité du demandeur":
            valeur = champ.get("stringValue", "").strip()

            if not valeur:
                return False

            # Exemple valeur : "75 - Paris"
            code_insee = valeur.split("-")[0].strip()

            return code_insee in set(departements_actifs)

    # Champ non trouvé
    return False


def _create_or_update_dossier_from_ds_data(
    dossier_data: dict | None,
    active_departement_insee_codes: Iterable[str],
    demarche: Demarche | None = None,
    iterator: int | None = None,
):
    try:
        ds_id = dossier_data["id"]
        ds_dossier_number = dossier_data["number"]
        if demarche is None:
            demarche_number = dossier_data["demarche"]["number"]
            demarche = Demarche.objects.get(ds_number=demarche_number)

        must_create_or_update_dossier = _is_dossier_in_active_departement(
            dossier_data, active_departement_insee_codes
        )
        if not must_create_or_update_dossier:
            logger.info(
                "Dossier is not in an active departement",
                extra={
                    "demarche_ds_number": demarche.ds_number,
                    "dossier_ds_number": ds_dossier_number,
                },
            )
            return

        dossier, _ = Dossier.objects.get_or_create(
            ds_id=ds_id,
            defaults={
                "ds_demarche": demarche,
                "ds_number": ds_dossier_number,
            },
        )
        _save_dossier_data_and_refresh_dossier_and_projet_and_co(
            dossier, dossier_data, async_refresh=True
        )
    except Exception as e:
        if not isinstance(e, DsServiceException):
            extra = {
                "demarche_ds_number": demarche.ds_number,
                "dossier_ds_number": ds_dossier_number,
                "error": str(e),
            }
            if iterator is not None:
                extra["i"] = iterator
            logger.exception(
                "Error unhandled while saving dossier from DN", extra=extra
            )

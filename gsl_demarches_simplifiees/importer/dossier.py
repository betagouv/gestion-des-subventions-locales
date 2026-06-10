import logging
from typing import Iterable, NamedTuple

from django.contrib import messages
from django.utils import timezone

from gsl.celery import TASK_PRIORITY_HIGH, TASK_PRIORITY_LOW
from gsl_core.models import Departement
from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.importer.utils import (
    NOT_HANDLED_TERRITORIES,
    get_or_create_profile,
)
from gsl_demarches_simplifiees.models import Demarche, Dossier, DossierData
from gsl_projet.services.projet_services import ProjetService

logger = logging.getLogger(__name__)


class _PageState(NamedTuple):
    cursor: str | None
    has_more: bool
    has_error: bool


def save_demarche_dossiers_from_ds(demarche_number):
    """
    Récupère les dossiers, pendingDeletedDossiers et deletedDossiers de la démarche
    depuis Démarches Numériques et les enregistre / désactive.

    Les trois ensembles sont paginés indépendamment. Si tous ont une page suivante,
    un seul appel API les récupère simultanément ; sinon seuls les ensembles non
    épuisés sont inclus dans l'appel suivant.

    :param demarche_number: numéro de la démarche
    """
    demarche = Demarche.objects.get(ds_number=demarche_number)
    client = DsClient()

    if demarche.updated_since is None:
        _reinit_demarche_sync_state(demarche)

    api_updated_since = demarche.updated_since
    dossiers_cursor = demarche.sync_cursor or None
    pending_deleted_cursor = demarche.pending_deleted_cursor or None
    deleted_cursor = demarche.deleted_cursor or None

    handled_departement_insee_codes = _get_handled_departement_insee_codes()
    groupe_index = _get_or_refresh_groupe_index(demarche, demarche_number)

    dossiers_count = 0
    has_more_dossiers = has_more_pending = has_more_deleted = True
    any_request_error = False
    dossiers_any_error = pending_any_error = deleted_any_error = False

    while has_more_dossiers or has_more_pending or has_more_deleted:
        demarche_data, has_errors = client.fetch_demarche_page(
            demarche_number,
            updated_since=api_updated_since,
            dossiers_after=dossiers_cursor,
            pending_deleted_after=pending_deleted_cursor,
            deleted_after=deleted_cursor,
            include_dossiers=has_more_dossiers,
            include_pending_deleted=has_more_pending,
            include_deleted=has_more_deleted,
        )

        if has_errors:
            any_request_error = True

        dossiers_result = pending_result = deleted_result = None

        if has_more_dossiers:
            dossiers_result, count = _process_dossiers_page(
                demarche_data["dossiers"],
                demarche,
                handled_departement_insee_codes,
                groupe_index,
            )
            dossiers_count += count
            if dossiers_result.has_error:
                dossiers_any_error = True

        if has_more_pending:
            pending_result = _process_deactivation_page(
                demarche_data["pendingDeletedDossiers"],
                Dossier.RAISON_DESACTIVATION_CORBEILLE,
                demarche.ds_number,
                "Error unhandled while deactivating pending deleted dossier",
            )
            if pending_result.has_error:
                pending_any_error = True

        if has_more_deleted:
            deleted_result = _process_deactivation_page(
                demarche_data["deletedDossiers"],
                Dossier.RAISON_DESACTIVATION_SUPPRIME,
                demarche.ds_number,
                "Error unhandled while deactivating deleted dossier",
            )
            if deleted_result.has_error:
                deleted_any_error = True

        has_more_dossiers, dossiers_cursor = _advance_stream(
            dossiers_result, dossiers_cursor
        )
        has_more_pending, pending_deleted_cursor = _advance_stream(
            pending_result, pending_deleted_cursor
        )
        has_more_deleted, deleted_cursor = _advance_stream(
            deleted_result, deleted_cursor
        )

        _save_cursors_after_page(
            demarche,
            any_request_error=any_request_error,
            dossiers_cursor=dossiers_cursor,
            dossiers_any_error=dossiers_any_error,
            pending_deleted_cursor=pending_deleted_cursor,
            pending_any_error=pending_any_error,
            deleted_cursor=deleted_cursor,
            deleted_any_error=deleted_any_error,
        )

    logger.info(
        "Demarche dossiers has been updated from DN",
        extra={
            "demarche_ds_number": demarche_number,
            "dossiers_count": dossiers_count,
        },
    )


def _get_or_refresh_groupe_index(demarche: Demarche, demarche_number: int) -> dict:
    groupe_index = _build_groupe_index_from_demarche(demarche)
    if not groupe_index:
        from gsl_demarches_simplifiees.importer.demarche import save_demarche_from_ds

        save_demarche_from_ds(demarche_number)
        demarche.refresh_from_db()
        groupe_index = _build_groupe_index_from_demarche(demarche)
    return groupe_index


def _process_dossiers_page(
    page: dict,
    demarche: Demarche,
    handled_departement_insee_codes: Iterable[str],
    groupe_index: dict,
) -> tuple["_PageState", int]:
    has_error = False
    count = 0
    for dossier_data in page["nodes"]:
        count += 1
        if dossier_data is None:
            logger.info(
                "Dossier data is empty",
                extra={"demarche_ds_number": demarche.ds_number, "i": count},
            )
            continue
        try:
            _create_or_update_dossier_from_ds_data(
                dossier_data,
                handled_departement_insee_codes,
                demarche,
                groupe_index=groupe_index,
            )
        except Exception as e:
            has_error = True
            logger.exception(
                "Error unhandled while saving dossier from DN",
                extra={
                    "demarche_ds_number": demarche.ds_number,
                    "dossier_ds_number": dossier_data["number"],
                    "error": str(e),
                    "i": count,
                },
            )
    return (
        _PageState(
            cursor=page["pageInfo"]["endCursor"],
            has_more=page["pageInfo"]["hasNextPage"],
            has_error=has_error,
        ),
        count,
    )


def _process_deactivation_page(
    page: dict, raison: str, demarche_ds_number: int, log_message: str
) -> "_PageState":
    has_error = False
    for deleted_data in page["nodes"]:
        try:
            _deactivate_deleted_dossier(deleted_data, raison)
        except Exception as e:
            has_error = True
            logger.exception(
                log_message,
                extra={
                    "demarche_ds_number": demarche_ds_number,
                    "dossier_ds_number": deleted_data.get("number"),
                    "error": str(e),
                },
            )
    return _PageState(
        cursor=page["pageInfo"]["endCursor"],
        has_more=page["pageInfo"]["hasNextPage"],
        has_error=has_error,
    )


def _advance_stream(
    result: "_PageState | None", current_cursor: str | None
) -> tuple[bool, str | None]:
    if result is None:
        return False, current_cursor
    # An empty connection returns endCursor=None (with hasNextPage=False); keep the
    # cursor we already have instead of resetting the stream to the beginning.
    next_cursor = current_cursor if result.cursor is None else result.cursor
    return result.has_more, next_cursor


def _save_cursors_after_page(
    demarche: "Demarche",
    *,
    any_request_error: bool,
    dossiers_cursor: str | None,
    dossiers_any_error: bool,
    pending_deleted_cursor: str | None,
    pending_any_error: bool,
    deleted_cursor: str | None,
    deleted_any_error: bool,
):
    if any_request_error:
        return

    update_fields = []
    if not dossiers_any_error:
        demarche.sync_cursor = dossiers_cursor or ""
        update_fields.append("sync_cursor")
    if not pending_any_error:
        demarche.pending_deleted_cursor = pending_deleted_cursor or ""
        update_fields.append("pending_deleted_cursor")
    if not deleted_any_error:
        demarche.deleted_cursor = deleted_cursor or ""
        update_fields.append("deleted_cursor")

    if update_fields:
        demarche.save(update_fields=update_fields)


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


def create_or_update_dossier_from_ds_number(ds_number: str):
    client = DsClient()
    dossier_data = client.get_one_dossier(ds_number)
    handled_departement_insee_codes = _get_handled_departement_insee_codes()
    return _create_or_update_dossier_from_ds_data(
        dossier_data, handled_departement_insee_codes
    )


def import_one_dossier_from_ds(dossier_number: int):
    """
    Récupère un dossier sur DN et le crée dans Turgot si :
    - sa démarche est présente dans Turgot
    - il n'existe pas encore dans Turgot

    Retourne un tuple (level, message) à la manière de save_one_dossier_from_ds.
    """
    client = DsClient()
    try:
        dossier_data = client.get_one_dossier(dossier_number)
    except DsServiceException as e:
        logger.warning(
            f"Impossible de récupérer le dossier #{dossier_number} depuis Démarches Numériques.",
            extra={
                "dossier_ds_number": dossier_number,
                "error": str(e),
            },
        )
        message = f"Impossible de récupérer le dossier #{dossier_number} depuis Démarches Numériques."
        if str(e):
            message += f" Erreur : {str(e)}"
        return (messages.WARNING, message)

    demarche_number = dossier_data["demarche"]["number"]

    if not Demarche.objects.filter(ds_number=demarche_number).exists():
        logger.info(
            "Démarche absente de Turgot, import ignoré",
            extra={
                "dossier_ds_number": dossier_number,
                "demarche_ds_number": demarche_number,
            },
        )
        return (
            messages.WARNING,
            f"La démarche n°{demarche_number} n'est pas présente sur Turgot.",
        )

    if Dossier.objects.filter(ds_number=dossier_number).exists():
        logger.info(
            "Dossier déjà présent dans Turgot, import ignoré",
            extra={"dossier_ds_number": dossier_number},
        )
        return (
            messages.WARNING,
            f"Le dossier #{dossier_number} existe déjà sur Turgot.",
        )

    handled_departement_insee_codes = _get_handled_departement_insee_codes()
    is_handled, departement = _is_dossier_in_handled_departement(
        dossier_data, handled_departement_insee_codes
    )
    if not is_handled:
        logger.info(
            "Dossier dans un territoire non géré, import ignoré",
            extra={"dossier_ds_number": dossier_number, "departement": departement},
        )
        return (
            messages.WARNING,
            f"Le dossier #{dossier_number} appartient au territoire « {departement} » qui n'est pas géré sur Turgot.",
        )

    # Import interactif d'un seul dossier (admin) : le refresh associé doit
    # passer devant la sync de fond, d'où la priorité haute.
    _create_or_update_dossier_from_ds_data(
        dossier_data,
        handled_departement_insee_codes,
        refresh_priority=TASK_PRIORITY_HIGH,
    )
    return (
        messages.SUCCESS,
        f"Le dossier #{dossier_number} a été importé avec succès.",
    )


def refresh_dossier_from_saved_data(dossier: Dossier):
    dossier_converter = DossierConverter(dossier.ds_data.raw_data, dossier)
    dossier_converter.fill_unmapped_fields()
    dossier_converter.convert_all_fields()
    dossier_converter.associate_perimetre()
    try:
        dossier.save()
    except Exception as e:
        logger.exception(str(e), extra={"dossier_ds_number": dossier.ds_number})
        raise e

    ProjetService.create_or_update_projet_and_co_from_dossier(dossier.ds_number)


def refresh_dossier_instructeurs(
    dossier_data, dossier: Dossier, groupe_index: dict | None = None
):
    """
    Refreshes the instructeurs associated with a dossier based on data from Démarche Numérique.

    The DN payload only ships ``groupeInstructeur.id`` for the dossier; the list of
    instructeurs is reconstructed locally from ``Demarche.raw_ds_data`` via
    ``groupe_index``: ``{groupe_ds_id: [{"id": ..., "email": ...}, ...]}``.

    If ``groupe_index`` is None, it is built from ``dossier.ds_demarche``. If the
    dossier's groupe id is missing from the mapping (groupe added on DN since the
    last ``save_demarche_from_ds``), refresh the demarche once and retry; if still
    unknown, log a warning and leave instructeurs untouched.

    Assume ds_instructeur has been prefetch_related on dossier
    Noop if no changes, check only IDs does not check emails.
    """
    if "groupeInstructeur" not in dossier_data:
        # Should not happen except in tests
        return
    groupe_id = dossier_data["groupeInstructeur"].get("id")
    if not groupe_id:
        return

    if groupe_index is None:
        groupe_index = _build_groupe_index_from_demarche(dossier.ds_demarche)

    instructeurs_data = groupe_index.get(groupe_id)
    if instructeurs_data is None:
        from gsl_demarches_simplifiees.importer.demarche import save_demarche_from_ds

        save_demarche_from_ds(dossier.ds_demarche.ds_number)
        dossier.ds_demarche.refresh_from_db()
        refreshed = _build_groupe_index_from_demarche(dossier.ds_demarche)
        groupe_index.clear()
        groupe_index.update(refreshed)
        instructeurs_data = groupe_index.get(groupe_id)

    if instructeurs_data is None:
        logger.warning(
            "Unknown groupeInstructeur id when refreshing dossier instructeurs",
            extra={
                "dossier_ds_number": dossier.ds_number,
                "groupe_ds_id": groupe_id,
            },
        )
        return

    # Remove instructeurs that are not in the new data
    for profile in dossier.ds_instructeurs.all():
        if profile.ds_id not in (i["id"] for i in instructeurs_data):
            dossier.ds_instructeurs.remove(profile)

    # Add instructeurs that are not already in the dossier
    dossier_instructeurs_ids = [p.ds_id for p in dossier.ds_instructeurs.all()]
    for instructeur_data in instructeurs_data:
        if instructeur_data["id"] not in dossier_instructeurs_ids:
            instructeur = get_or_create_profile(
                instructeur_data["id"], instructeur_data["email"]
            )
            dossier.ds_instructeurs.add(instructeur)


def _build_groupe_index_from_demarche(demarche: Demarche) -> dict[str, list[dict]]:
    """
    Build ``{groupe_ds_id: [{"id": profile_ds_id, "email": profile_email}, ...]}``
    from ``demarche.raw_ds_data["groupeInstructeurs"]``. Returns an empty dict if
    the raw data is missing.
    """
    raw = demarche.raw_ds_data or {}
    groupes = raw.get("groupeInstructeurs") or []
    return {
        groupe["id"]: [
            {"id": instr["id"], "email": instr["email"]}
            for instr in groupe.get("instructeurs", [])
        ]
        for groupe in groupes
        if "id" in groupe
    }


### Private methods


def _deactivate_deleted_dossier(deleted_dossier_data: dict, raison: str):
    ds_number = deleted_dossier_data["number"]
    try:
        dossier = Dossier.objects.get(ds_number=ds_number)
    except Dossier.DoesNotExist:
        logger.info(
            "Deleted dossier not found in Turgot, skipping",
            extra={"dossier_ds_number": ds_number},
        )
        return

    if dossier.is_active or dossier.raison_desactivation != raison:
        dossier.is_active = False
        dossier.raison_desactivation = raison
        dossier.save(update_fields=["is_active", "raison_desactivation"])


def _save_dossier_data_and_refresh_dossier_and_projet_and_co(
    dossier: Dossier,
    dossier_data: dict,
    async_refresh: bool = False,
    refresh_only_if_dossier_has_been_updated: bool = True,
    groupe_index: dict | None = None,
    refresh_priority: int = TASK_PRIORITY_LOW,
):
    if refresh_only_if_dossier_has_been_updated:
        must_refresh_dossier = _has_dossier_been_updated_on_ds(dossier, dossier_data)
    else:
        must_refresh_dossier = True

    refresh_dossier_instructeurs(dossier_data, dossier, groupe_index=groupe_index)
    if getattr(dossier, "ds_data", None) is None:
        DossierData.objects.create(dossier=dossier, raw_data=dossier_data)
    else:
        dossier.ds_data.raw_data = dossier_data
        dossier.ds_data.save()
    dossier.save()

    if must_refresh_dossier:
        if async_refresh:
            from gsl_demarches_simplifiees.tasks import (
                task_refresh_dossier_from_saved_data,
            )

            task_refresh_dossier_from_saved_data.apply_async(
                (dossier.ds_number,), priority=refresh_priority
            )
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


def _get_handled_departement_insee_codes():
    return Departement.objects.exclude(
        insee_code__in=NOT_HANDLED_TERRITORIES
    ).values_list("insee_code", flat=True)


def _create_or_update_dossier_from_ds_data(
    dossier_data: dict | None,
    handled_departement_insee_codes: Iterable[str],
    demarche: Demarche | None = None,
    groupe_index: dict | None = None,
    refresh_priority: int = TASK_PRIORITY_LOW,
):
    ds_id = dossier_data["id"]
    ds_dossier_number = dossier_data["number"]
    if demarche is None:
        demarche_number = dossier_data["demarche"]["number"]
        demarche = Demarche.objects.get(ds_number=demarche_number)

    must_create_or_update_dossier, _ = _is_dossier_in_handled_departement(
        dossier_data, handled_departement_insee_codes
    )
    if not must_create_or_update_dossier:
        logger.info(
            "Dossier is not in a handled departement",
            extra={
                "demarche_ds_number": demarche.ds_number,
                "dossier_ds_number": ds_dossier_number,
            },
        )
        return

    try:
        dossier = Dossier.objects.get(ds_id=ds_id)
    except Dossier.DoesNotExist:
        dossier = Dossier.objects.create(
            ds_id=ds_id,
            ds_number=ds_dossier_number,
            ds_demarche=demarche,
        )
        DossierData.objects.create(dossier=dossier)

    _save_dossier_data_and_refresh_dossier_and_projet_and_co(
        dossier,
        dossier_data,
        async_refresh=True,
        refresh_only_if_dossier_has_been_updated=False,
        groupe_index=groupe_index,
        refresh_priority=refresh_priority,
    )


def _is_dossier_in_handled_departement(
    raw_data: dict, handled_departement_insee_codes: Iterable[str]
) -> tuple[bool, str]:
    champs = raw_data.get("champs", [])

    for champ in champs:
        if champ.get("label") == "Département ou collectivité du demandeur":
            valeur = champ.get("stringValue", "").strip()

            if not valeur:
                return False, valeur

            # Exemple valeur : "75 - Paris"
            code_insee = valeur.split("-")[0].strip()

            return code_insee in set(handled_departement_insee_codes), valeur

    # Champ non trouvé
    return False, "inconnu"


def _reinit_demarche_sync_state(demarche: Demarche):
    new_updated_since = demarche.created_at
    demarche.updated_since = new_updated_since
    demarche.sync_cursor = ""
    demarche.pending_deleted_cursor = ""
    demarche.deleted_cursor = ""
    demarche.save(
        update_fields=[
            "updated_since",
            "sync_cursor",
            "pending_deleted_cursor",
            "deleted_cursor",
        ]
    )

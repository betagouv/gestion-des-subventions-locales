import re
from logging import getLogger

from gsl_core.models import Arrondissement, Departement, Perimetre
from gsl_demarches_simplifiees.models import CategorieDetr, Dossier

logger = getLogger(__name__)


def get_departement_from_field_label(label: str) -> Departement | None:
    """
    Extract département from a field label following the pattern:
    "Catégories prioritaires (87 - Haute-Vienne)", "Catégories prioritaires (91 - Essonne)", etc.
    """
    match = re.match(r".*\(\s*([^-\s]+)\s*-\s*[^)]+\s*\)", label)
    if not match:
        raise ValueError(f"Departement not found in field label: {label}")
    insee_code = match.group(1).strip()
    try:
        return Departement.objects.get(insee_code=insee_code)
    except Departement.DoesNotExist:
        logger.exception(
            "Departement not found.",
            extra={
                "label": label,
                "insee_code": insee_code,
            },
        )
        raise


def get_arrondissement_from_value(value: str) -> Arrondissement | None:
    """
    Extract arrondissement name and department code from a field value following the pattern:
    "67 - Bas-Rhin - arrondissement de Haguenau-Wissembourg" => "Haguenau-Wissembourg"
    "10 - Aube - arrondissement de Bar-sur-Aube" => "Bar-sur-Aube"
    Then return the Arrondissement object with the given name and department.
    """
    match = re.match(
        r"^\s*(\d{1,3}[AB]?)\s*-\s*.+arrondissement\s*de\s*(.+)$",
        value,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Arrondissement not found in field value: {value}")
    departement_insee_code = match.group(1).strip()
    name = match.group(2).strip()
    try:
        return Arrondissement.objects.get(
            name=name, departement__insee_code=departement_insee_code
        )
    except Arrondissement.DoesNotExist:
        logger.exception(
            "Arrondissement not found.",
            extra={
                "value": value,
            },
        )
        raise


def get_departement_from_value(value: str) -> Departement | None:
    """
    Extract departement insee code from a field value following the pattern:
    "87 - Haute-Vienne" => insee_code "87"
    "91 - Essonne" => insee_code "91"
    "10 - Aube" => insee_code "10"
    "2A - Corse-du-Sud" => insee_code "2A"
    "976 - Nouvelle-Calédonie" => insee_code "976"
    Then return the Departement object with the given insee code.
    """
    match = re.match(r"^\s*(\d{1,3}[AB]?)\s*-\s*.+", value.strip())
    if not match:
        raise ValueError(f"Departement not found in field value: {value}")
    insee_code = match.group(1).strip()
    try:
        return Departement.objects.get(insee_code=insee_code)
    except Departement.DoesNotExist:
        logger.exception(
            "Departement not found.",
            extra={
                "value": value,
                "insee_code": insee_code,
            },
        )
        raise


def get_perimetre_from_dossier(dossier: Dossier) -> Perimetre | None:
    arrondissement = dossier.porteur_de_projet_arrondissement
    if arrondissement is not None:
        try:
            return Perimetre.objects.get(arrondissement=arrondissement)
        except Perimetre.DoesNotExist:
            logger.exception(
                "Perimetre not found.",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "arrondissement": arrondissement,
                },
            )

    departement = dossier.porteur_de_projet_departement
    if departement is not None:
        try:
            return Perimetre.objects.get(departement=departement, arrondissement=None)
        except Perimetre.DoesNotExist:
            logger.exception(
                "Perimetre not found.",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "departement": departement,
                },
            )

    logger.warning(
        "Dossier is missing arrondissement and departement.",
        extra={
            "dossier_ds_number": dossier.ds_number,
            "arrondissement": dossier.porteur_de_projet_arrondissement,
            "departement": dossier.porteur_de_projet_departement,
        },
    )

    return None


def get_categorie_detr_from_value(
    value: str, departement: Departement, ds_demarche_number: str
) -> CategorieDetr | None:
    try:
        return CategorieDetr.objects.get(
            demarche__ds_number=ds_demarche_number,
            label=value,
            departement=departement,
        )
    except CategorieDetr.DoesNotExist:
        logger.exception(
            "CategorieDetr not found.",
            extra={
                "ds_demarche_number": ds_demarche_number,
                "value": value,
                "departement": departement,
            },
        )
        raise

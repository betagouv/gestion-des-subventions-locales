import re

from gsl_core.models import Arrondissement, Departement


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
        raise ValueError(f"Departement not found: {insee_code}")


def get_arrondissement_from_value(value: str) -> Arrondissement | None:
    """
    Extract arrondissement name from a field value following the pattern:
    "67 - Bas-Rhin - arrondissement de Haguenau-Wissembourg" => "Haguenau-Wissembourg"
    "10 - Aube - arrondissement de Bar-sur-Aube" => "Bar-sur-Aube"
    Then return the Arrondissement object with the given name.
    """
    match = re.match(r".*arrondissement\s*de\s*(.+)$", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"Arrondissement not found in field value: {value}")
    name = match.group(1).strip()
    try:
        return Arrondissement.objects.get(name=name)
    except Arrondissement.DoesNotExist:
        raise ValueError(f"Arrondissement not found: {name}")


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
        raise ValueError(f"Departement not found: {insee_code}")

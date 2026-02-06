import re

from gsl_core.models import Departement


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

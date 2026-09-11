def resolve_departement(code):
    from gsl_core.models import Departement

    if not code:
        return None
    # DGCL CSVs zero-pad to 3 chars (e.g. "001") but Departement.insee_code uses
    # 2 chars for mainland ("01") and 3 for overseas ("971"-"976") or Corsica ("2A").
    stripped = code.lstrip("0") or "0"
    candidates = dict.fromkeys([code, stripped.zfill(2), stripped.zfill(3)])
    for candidate in candidates:
        try:
            return Departement.objects.get(insee_code=candidate)
        except Departement.DoesNotExist:
            pass
    return None


def resolve_commune(code_insee):
    from gsl_core.models import Commune

    if not code_insee:
        return None
    try:
        return Commune.objects.get(insee_code=code_insee)
    except Commune.DoesNotExist:
        return None

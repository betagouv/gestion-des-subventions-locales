from gsl_core.models import Commune, Departement

DEPARTEMENTS: dict[str, Departement] = {}
COMMUNES: dict[str, Commune] = {}


def resolve_departement(code):
    """Résout un code INSEE département en `Departement`. Charge tous les
    départements en mémoire au premier appel plutôt que de faire une requête
    par ligne importée (une centaine de lignes, ça tient largement en RAM)."""
    if not code:
        return None

    if not DEPARTEMENTS:
        for d in Departement.objects.all():
            DEPARTEMENTS[d.insee_code] = d

    # DGCL CSVs zero-pad to 3 chars (e.g. "001") but Departement.insee_code uses
    # 2 chars for mainland ("01") and 3 for overseas ("971"-"976") or Corsica ("2A").
    stripped = code.lstrip("0") or "0"
    for candidate in dict.fromkeys([code, stripped.zfill(2), stripped.zfill(3)]):
        if candidate in DEPARTEMENTS:
            return DEPARTEMENTS[candidate]
    return None


def resolve_commune(code_insee):
    """Résout un code INSEE commune en `Commune`. Charge toutes les communes
    en mémoire au premier appel plutôt que de faire une requête par ligne
    importée."""
    if not code_insee:
        return None

    if not COMMUNES:
        for c in Commune.objects.all():
            COMMUNES[c.insee_code] = c

    return COMMUNES.get(code_insee)


def reset_geo_cache():
    """Vide le cache mémoire de `resolve_departement`/`resolve_commune`. À
    utiliser dans les tests (fixture autouse) : la base est réinitialisée à
    chaque test mais pas ce cache en mémoire, qui référencerait alors des
    objets d'un test précédent."""
    global DEPARTEMENTS, COMMUNES
    DEPARTEMENTS = {}
    COMMUNES = {}

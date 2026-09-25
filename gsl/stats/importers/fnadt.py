import io
import logging

import openpyxl
from django.db import transaction

from gsl.core.models import Commune

from ..models import Subvention
from .utils import (
    InvalidRow,
    log_invalidated_lines,
    parse_excel_decimal,
    resolve_commune,
)

logger = logging.getLogger(__name__)

# La feuille "Feuil1" du classeur n'est qu'un tableau croisé dynamique
# récapitulatif : seule "Liste" contient les lignes de projets à importer.
FNADT_SHEET_NAME = "Liste"

# Le FNADT n'a pas de "dispositif" propre côté DS (ce n'est pas un import
# DGCL) : on retient une constante, comme pour le Fonds Vert. Programme 112
# ("Impulsion et coordination de la politique d'aménagement du territoire"),
# qui finance le FNADT — la colonne "BOP" du fichier le corrobore le plus
# souvent (préfixe "0112-...") mais est saisie à la main et pas assez fiable
# pour en dériver le programme ligne à ligne.
FNADT_DISPOSITIF = "FNADT"
FNADT_PROGRAMME = 112


@transaction.atomic
def import_fnadt_subventions(content: bytes):
    """Importe le recensement FNADT depuis le contenu brut du classeur Excel
    (`content`, lu par l'appelant — cf. `import_subventions_fnadt`).

    Comme les données DGCL (cf. Subvention.__doc__), ce recensement est
    republié dans son intégralité à chaque mise à jour et n'a pas
    d'identifiant stable par ligne : purge + reconstruction complète à
    chaque import plutôt qu'un upsert. La transaction évite de se retrouver
    avec une table vidée si le réimport plante en cours de route."""
    workbook = openpyxl.load_workbook(
        io.BytesIO(content), read_only=True, data_only=True
    )
    worksheet = workbook[FNADT_SHEET_NAME]
    rows = worksheet.iter_rows(values_only=True)
    header = next(rows)
    columns = _resolve_fnadt_columns(header)

    nb_deleted, _ = Subvention.objects.filter(source=Subvention.SOURCE_FNADT).delete()
    logger.info(f"{nb_deleted} lignes FNADT existantes supprimées avant réimport")

    subventions = []
    invalid_rows: list[InvalidRow] = []

    for line_num, row in enumerate(rows, start=2):
        if all(value is None for value in row):
            continue
        try:
            subventions.append(_build_fnadt_subvention(columns, row))
        except FnadtRowSkipped as e:
            invalid_rows.append(InvalidRow(line_num, e.reason))
        except ValueError as e:
            invalid_rows.append(InvalidRow(line_num, str(e)))

    Subvention.objects.bulk_create(subventions)
    logger.info(
        f"{len(subventions)} lignes FNADT importées, {len(invalid_rows)} lignes invalidées"
    )
    log_invalidated_lines(logger, invalid_rows)

    return {"imported": len(subventions), "skipped": len(invalid_rows)}


class FnadtRowSkipped(ValueError):
    """Levée par `_build_fnadt_subvention` pour signaler qu'une ligne doit
    être ignorée. `reason` est un libellé regroupable (sert de clé pour le
    bilan par type d'erreur)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


_FNADT_COLUMN_NAMES = {
    "annee": "Année",
    "code_lieu": "Code INSEE commune/ Code SIREN EPCI du lieu du projet soutenu",
    "intitule": "Commentaires",
    "cout_total": "Coût total du projet",
    "montant_attribue": "Montant subvention FNADT attribuée (AE)",
}


def _resolve_fnadt_columns(header):
    """Retrouve l'index des quelques colonnes utiles, par nom plutôt que par
    position : ce recensement est une déclaration manuelle et les colonnes
    ne sont pas toujours dans le même ordre d'une mise à jour à l'autre."""
    return {
        field_name: _find_fnadt_column(header, name)
        for field_name, name in _FNADT_COLUMN_NAMES.items()
    }


def _find_fnadt_column(header, name):
    prefix = name.lower()
    for i, title in enumerate(header):
        if title and str(title).strip().lower().startswith(prefix):
            return i
    raise ValueError(f"Colonne introuvable dans l'en-tête FNADT : {name!r}")


def _build_fnadt_subvention(columns, row) -> Subvention:
    """Lève `FnadtRowSkipped` si la ligne doit être ignorée (année
    manquante, ou SIREN non résolvable). La colonne "Code INSEE
    commune/Code SIREN EPCI" contient, selon les lignes, soit un code INSEE
    commune (résolu via la table `Commune`), soit directement un SIREN
    d'EPCI (9 chiffres) — cf. `_resolve_fnadt_siren`."""

    annee = row[columns["annee"]]
    if not annee:
        raise FnadtRowSkipped("année manquante")

    siren, commune = _resolve_fnadt_siren(
        _normalize_fnadt_code(row[columns["code_lieu"]])
    )

    return Subvention(
        source=Subvention.SOURCE_FNADT,
        exercice=annee,
        dispositif=FNADT_DISPOSITIF,
        programme=FNADT_PROGRAMME,
        siren=siren,
        intitule=(row[columns["intitule"]] or "").strip(),
        departement=commune.departement if commune else None,
        commune=commune,
        cout_total=parse_excel_decimal(row[columns["cout_total"]]),
        montant_attribue=parse_excel_decimal(row[columns["montant_attribue"]]),
    )


def _resolve_fnadt_siren(code: str) -> tuple[str, Commune | None]:
    """Résout le SIREN d'une ligne à partir de la colonne "Code INSEE
    commune/Code SIREN EPCI", qui contient selon les lignes soit un code
    INSEE commune (5 caractères), soit directement le SIREN (9 chiffres) ou
    le SIRET (14 chiffres, SIREN + NIC) d'un EPCI. Lève `FnadtRowSkipped` si
    aucun SIREN n'en ressort."""
    if code.isdigit() and len(code) == 14:
        # Un SIRET (établissement) : les 9 premiers chiffres sont le SIREN.
        code = code[:9]

    if code.isdigit() and len(code) == 9:
        # Déjà un SIREN d'EPCI, directement exploitable : pas de commune à
        # résoudre (le projet est porté par l'EPCI, pas par une commune).
        return code, None

    if code.isdigit() and len(code) == 4:
        # Excel a stocké la cellule comme un nombre, ce qui a fait sauter le
        # zéro de tête d'un code INSEE commune (ex. "01234" -> 1234).
        code = code.zfill(5)

    commune = resolve_commune(code)
    if commune is None:
        raise FnadtRowSkipped("commune introuvable")
    if not commune.siren:
        raise FnadtRowSkipped("commune sans SIREN enregistré")
    return commune.siren, commune


def _normalize_fnadt_code(value) -> str:
    """Normalise la valeur brute de la colonne "Code INSEE commune/Code
    SIREN EPCI" en un code numérique unique, prêt pour `_resolve_fnadt_siren`.

    Gère les variations observées dans ce recensement saisi à la main :
    - type `openpyxl` non-`str` (`int`, ou `float` quand Excel a stocké la
      cellule comme un nombre décimal, ex. 1234.0) ;
    - espaces de séparation par milliers dans un SIREN (ex. "200 023 075") ;
    - cellule renseignant à la fois le code INSEE commune ET le SIREN (ou le
      SIRET) de l'EPCI, une valeur par ligne (ex. "25335\n200 023 075") : on
      retient alors directement le SIREN/SIRET plutôt que le code INSEE
      (cf. `_resolve_fnadt_siren` pour la réduction du SIRET en SIREN)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    value = str(value)

    codes = [
        line.replace(" ", "").strip() for line in value.splitlines() if line.strip()
    ]
    if not codes:
        return ""

    siren_or_siret = next(
        (code for code in codes if code.isdigit() and len(code) in (9, 14)), None
    )
    return siren_or_siret or codes[0]

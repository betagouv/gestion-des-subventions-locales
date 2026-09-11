import csv
import io
import logging

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from gsl.projet.utils.utils import compute_taux
from gsl_core.models import Commune

logger = logging.getLogger(__name__)

SIREN_INSEE_DATASET_ID = "630f5173873064dd369479b4"
SIREN_INSEE_DATASET_API_URL = (
    f"https://www.data.gouv.fr/api/1/datasets/{SIREN_INSEE_DATASET_ID}/"
)


class Command(BaseCommand):
    """
    python manage.py import_commune_siren

    Associe à chaque Commune existante (identifiée par son insee_code, déjà
    importée via `import_cog`) son numéro SIREN, depuis la table de
    correspondance SIREN/INSEE publiée par la DGCL/Banatic sur data.gouv.fr :
    https://www.data.gouv.fr/datasets/table-de-correspondance-entre-ndeg-siren-et-code-insee-des-communes

    Le jeu de données est interrogé via l'API data.gouv.fr (comme
    `gsl/stats/importers/dgcl.py`) pour toujours récupérer la ressource CSV
    la plus récente plutôt qu'une URL figée. Ne crée jamais de Commune : les
    codes INSEE absents de la base sont simplement ignorés.
    """

    help = "Associe le SIREN de chaque commune depuis la table de correspondance SIREN/INSEE (Banatic)"

    @transaction.atomic
    def handle(self, *args, **options):
        siren_by_insee_code = self.parse_csv_rows(self.fetch_csv_rows())
        updated = self.apply_siren(siren_by_insee_code)
        communes_count = Commune.objects.count()

        self.stdout.write(
            self.style.SUCCESS(
                f"{updated} commune(s) mise(s) à jour sur {len(siren_by_insee_code)} "
                f"ligne(s) exploitables du fichier. Pour rappel il y a {communes_count} objets Communes,"
                f"ce qui représente {compute_taux(updated, communes_count, 2)}% des communes"
            )
        )

    def fetch_csv_rows(self):
        response = requests.get(SIREN_INSEE_DATASET_API_URL, timeout=30)
        response.raise_for_status()
        dataset = response.json()

        csv_resources = [
            r
            for r in dataset.get("resources", [])
            if r.get("format", "").lower() == "csv"
        ]
        if not csv_resources:
            raise CommandError(
                f"Aucune ressource CSV trouvée sur {SIREN_INSEE_DATASET_API_URL}"
            )
        # Une seule ressource CSV est publiée en temps normal ; on prend la
        # plus récemment mise à jour par prudence si jamais il y en avait
        # plusieurs (nouveau millésime ajouté sans retrait de l'ancien).
        resource = max(csv_resources, key=lambda r: r.get("last_modified") or "")
        url = resource["url"]

        self.stdout.write(f"Téléchargement de {url}…")
        csv_response = requests.get(url, timeout=60)
        csv_response.raise_for_status()
        # Le CSV Banatic est encodé en Latin-1 (accents) et délimité par ";".
        text = csv_response.content.decode("cp1252")
        return csv.DictReader(io.StringIO(text), delimiter=";")

    def parse_csv_rows(self, rows):
        siren_by_insee_code = {}
        for row in rows:
            siren = (row.get("siren") or "").strip()
            insee_code = (row.get("insee") or "").strip()
            if siren and insee_code:
                siren_by_insee_code[insee_code] = siren
        return siren_by_insee_code

    def apply_siren(self, siren_by_insee_code):
        communes = list(
            Commune.objects.filter(insee_code__in=siren_by_insee_code.keys())
        )
        for commune in communes:
            commune.siren = siren_by_insee_code[commune.insee_code]
        Commune.objects.bulk_update(communes, ["siren"], batch_size=1000)
        return len(communes)

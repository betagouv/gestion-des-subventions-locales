import csv
import io
import logging

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from gsl_core.models import Arrondissement, Commune, Departement, Region

logger = logging.getLogger(__name__)

COG_MILLESIME = 2026
COG_BASE_URL = "https://www.insee.fr/fr/statistiques/fichier/8740222"


class Command(BaseCommand):
    """
    python manage.py import_cog
    """

    help = (
        f"Import from INSEE Code Officiel Géographique {COG_MILLESIME} "
        "(régions, départements, arrondissements, communes)"
    )

    def fetch_csv(self, filename):
        url = f"{COG_BASE_URL}/{filename}"
        self.stdout.write(f"Téléchargement de {url}…")
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            raise CommandError(
                f"Impossible de télécharger {url} ({response.status_code})"
            )
        response.encoding = "utf-8"
        return csv.DictReader(io.StringIO(response.text))

    def report(self, verbose_name, created, updated):
        self.stdout.write(
            self.style.SUCCESS(
                f"{verbose_name} : {created} création(s), {updated} mise(s) à jour"
            )
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.import_regions()
        self.import_departements()
        self.import_arrondissements()
        self.import_communes()
        self.stdout.write(self.style.SUCCESS("Terminé."))

    def import_regions(self):
        created, updated = 0, 0
        for row in self.fetch_csv(f"v_region_{COG_MILLESIME}.csv"):
            _, is_created = Region.objects.update_or_create(
                insee_code=row["REG"],
                defaults={"name": row["LIBELLE"]},
            )
            created += is_created
            updated += not is_created
        self.report("Régions", created, updated)

    def import_departements(self):
        created, updated = 0, 0
        for row in self.fetch_csv(f"v_departement_{COG_MILLESIME}.csv"):
            _, is_created = Departement.objects.update_or_create(
                insee_code=row["DEP"],
                defaults={
                    "name": row["LIBELLE"],
                    "region_id": row["REG"],
                },
            )
            created += is_created
            updated += not is_created
        self.report("Départements", created, updated)

    def import_arrondissements(self):
        created, updated = 0, 0
        for row in self.fetch_csv(f"v_arrondissement_{COG_MILLESIME}.csv"):
            _, is_created = Arrondissement.objects.update_or_create(
                insee_code=row["ARR"],
                defaults={
                    "name": row["LIBELLE"],
                    "departement_id": row["DEP"],
                },
            )
            created += is_created
            updated += not is_created
        self.report("Arrondissements", created, updated)

    def import_communes(self):
        created, updated = 0, 0
        skipped = 0
        for row in self.fetch_csv(f"v_commune_{COG_MILLESIME}.csv"):
            # Only keep "communes de plein exercice", and skip "communes déléguées",
            # "communes associées", arrondissements (PLM)
            if row["TYPECOM"] != "COM":
                skipped += 1
                continue
            _, is_created = Commune.objects.update_or_create(
                insee_code=row["COM"],
                defaults={
                    "name": row["LIBELLE"],
                    "departement_id": row["DEP"],
                    "arrondissement_id": row["ARR"] or None,
                },
            )
            created += is_created
            updated += not is_created
        self.report("Communes", created, updated)
        if skipped:
            self.stdout.write(f"{skipped} ligne(s) ignorée(s) (COMD, COMA, ARM)")

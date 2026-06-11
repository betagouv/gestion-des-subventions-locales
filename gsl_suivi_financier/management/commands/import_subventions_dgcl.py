import logging

import requests
from django.core.management.base import BaseCommand

from gsl_suivi_financier.tasks import DGCL_API_URL, _import_csv_resource

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_dgcl
    """

    help = "Importe les subventions DGCL depuis data.gouv.fr"

    def handle(self, *args, **kwargs):
        self.stdout.write(f"Récupération du jeu de données depuis {DGCL_API_URL}…")

        response = requests.get(DGCL_API_URL, timeout=30)
        response.raise_for_status()
        dataset = response.json()

        resources = [
            r
            for r in dataset.get("resources", [])
            if r.get("format", "").lower() == "csv"
        ]
        self.stdout.write(f"Trouvé {len(resources)} ressources CSV.")

        for resource in resources:
            url = resource.get("url")
            if not url:
                continue
            title = resource.get("title", url)
            self.stdout.write(f"Import de : {title}…")
            nb_created, nb_updated, errors = _import_csv_resource(url)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  → {nb_created} créés, {nb_updated} mis à jour, {len(errors)} erreurs"
                )
            )
            for err in errors:
                self.stderr.write(
                    self.style.ERROR(
                        f"  Ligne {err['line']}: {err['error']} — {err['row']}"
                    )
                )

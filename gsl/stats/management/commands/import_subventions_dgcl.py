import logging

from django.core.management.base import BaseCommand

from gsl.stats.tasks import fetch_subventions_dgcl

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_dgcl

    Réimporte l'intégralité du jeu de données DGCL : les lignes DGCL
    existantes sont supprimées puis recréées depuis les CSV (cf.
    `Subvention.__doc__` et `fetch_subventions_dgcl` — pas d'upsert, doublons
    compris). Le détail des erreurs par ligne est journalisé (logger), pas
    affiché ici.
    """

    help = "Importe les subventions DGCL depuis data.gouv.fr"

    def handle(self, *args, **kwargs):
        self.stdout.write("Récupération et import du jeu de données DGCL…")

        bilan = fetch_subventions_dgcl()

        for title, stats in bilan.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"{title} : {stats['imported']} importés, {stats['errors']} erreurs"
                )
            )

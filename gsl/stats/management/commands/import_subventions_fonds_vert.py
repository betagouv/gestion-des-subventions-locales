import logging

from django.core.management.base import BaseCommand

from gsl.stats.importers.fonds_vert import import_fonds_vert_subventions

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_fonds_vert [--restart]

    Ne récupère par défaut que les dossiers modifiés depuis la dernière
    synchronisation complète réussie (état partagé avec la tâche Celery
    `fetch_subventions_fonds_vert`, via `date_derniere_modification__gte`).
    Utiliser --restart pour ignorer cette date et forcer un réimport complet
    de l'historique.
    """

    help = "Importe les subventions Fonds Vert depuis l'API datahub"

    def add_arguments(self, parser):
        parser.add_argument(
            "--restart",
            action="store_true",
            help=(
                "Ignore la date de dernière synchronisation stockée et "
                "réimporte tout l'historique depuis la page 1."
            ),
        )

    def handle(self, *args, restart, **kwargs):
        self.stdout.write("Récupération et import des subventions Fonds Vert…")

        import_fonds_vert_subventions(restart=restart)

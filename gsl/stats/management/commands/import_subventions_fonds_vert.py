import logging

from django.core.management.base import BaseCommand

from gsl.stats.importers.fonds_vert import import_fonds_vert_subventions

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_fonds_vert [--restart]

    Reprend automatiquement après la dernière page importée avec succès (curseur
    partagé avec la tâche Celery `fetch_subventions_fonds_vert`). Utiliser --restart
    pour forcer une reprise depuis la page 1.
    """

    help = "Importe les subventions Fonds Vert depuis l'API datahub"

    def add_arguments(self, parser):
        parser.add_argument(
            "--restart",
            action="store_true",
            help="Ignore le curseur de reprise et repart de la page 1.",
        )

    def handle(self, *args, restart, **kwargs):
        self.stdout.write("Récupération et import des subventions Fonds Vert…")

        import_fonds_vert_subventions(restart=restart)

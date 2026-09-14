import logging

from django.core.management.base import BaseCommand

from gsl.stats.importers.fonds_vert import import_fonds_vert_subventions

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_fonds_vert [--restart]
    (credentials lus depuis FONDS_VERT_USERNAME / FONDS_VERT_PASSWORD via settings.py)

    Reprend automatiquement après la dernière page importée avec succès (curseur
    partagé avec la tâche Celery `fetch_subventions_fonds_vert`). Utiliser --restart
    pour forcer une reprise depuis la page 1. Le détail (pages traitées, dossiers
    en erreur) est toujours journalisé (logger), pas affiché ici.
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

        bilan = import_fonds_vert_subventions(restart=restart)

        if not bilan:
            self.stderr.write(
                self.style.ERROR("Import annulé (cf. logs pour le détail).")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Import terminé : {bilan['created']} créés, "
                f"{bilan['updated']} mis à jour, {bilan['errors']} erreurs"
            )
        )

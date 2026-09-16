import logging

from django.core.management.base import BaseCommand

from ...importers.dgcl import import_dgcl_subventions

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_dgcl [--show-dsid]

    Réimporte l'intégralité du jeu de données DGCL : les lignes DGCL
    existantes sont supprimées puis recréées depuis les CSV (cf.
    `Subvention.__doc__` et `import_dgcl_subventions` — pas d'upsert, doublons
    compris). Le détail des lignes invalides est toujours journalisé
    (logger) ; les lignes ignorées en dispositif DSID (hors périmètre
    Turgot) sont masquées sauf avec --show-dsid.
    """

    help = "Importe les subventions DGCL depuis data.gouv.fr"

    def add_arguments(self, parser):
        parser.add_argument(
            "--show-dsid",
            action="store_true",
            help="Affiche aussi les lignes ignorées en dispositif DSID (masquées par défaut).",
        )

    def handle(self, *args, show_dsid, **kwargs):
        self.stdout.write("Récupération et import du jeu de données DGCL…")

        import_dgcl_subventions(show_dsid=show_dsid)

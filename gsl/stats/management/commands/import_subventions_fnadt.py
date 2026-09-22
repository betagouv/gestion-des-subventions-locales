import logging

from django.core.management.base import BaseCommand, CommandError

from ...importers.fnadt import import_fnadt_subventions

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_fnadt <fichier.xlsx>

    Réimporte l'intégralité du recensement FNADT à partir du classeur Excel
    passé en argument : les lignes FNADT existantes sont supprimées puis
    recréées (cf. `import_fnadt_subventions` — pas d'upsert, comme pour les
    données DGCL). Les lignes sans SIREN résolvable (commune introuvable ou
    sans SIREN enregistré) sont ignorées ; le détail des lignes ignorées est
    journalisé (logger).
    """

    help = "Importe le recensement des projets financés par le FNADT depuis un classeur Excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "fichier", help="Chemin du classeur Excel du recensement FNADT (DGCL)"
        )

    def handle(self, *args, **options):
        file_path = options["fichier"]
        self.stdout.write(f"Import du recensement FNADT depuis {file_path}…")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError as e:
            raise CommandError(f"Impossible de lire {file_path} : {e}")

        bilan = import_fnadt_subventions(content)

        self.stdout.write(
            self.style.SUCCESS(
                f"{bilan['imported']} lignes importées, {bilan['skipped']} ignorées"
            )
        )

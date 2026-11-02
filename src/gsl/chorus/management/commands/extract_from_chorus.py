from django.core.management.base import BaseCommand, CommandError

from ...importer import ChorusImportError, import_chorus_file


class Command(BaseCommand):
    """
    uv run python manage.py extract_from_chorus <fichier.xlsx>
    """

    help = (
        "Importe un export « Journal des pièces » de Chorus (XLSX) dans SuiviFinancier."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file", help="Chemin vers le fichier XLSX exporté de Chorus"
        )

    def handle(self, *args, **options):
        path = options["file"]
        try:
            result = import_chorus_file(path)
        except FileNotFoundError:
            raise CommandError(f"Fichier introuvable : {path}")
        except ChorusImportError as e:
            raise CommandError(str(e))

        self.stdout.write(
            self.style.SUCCESS(f"{result.imported} nouvelle(s) ligne(s).")
        )
        self.stdout.write(f"{result.matched} rattachée(s) à un dossier connu (DN).")
        if result.duplicate:
            self.stdout.write(f"{result.duplicate} déjà présente(s), ignorée(s).")
        if result.skipped:
            self.stdout.write(
                f"{result.skipped} ligne(s) ignorée(s) (sans EJ ou sans montant)."
            )

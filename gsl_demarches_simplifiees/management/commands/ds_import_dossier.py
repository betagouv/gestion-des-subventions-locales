from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.importer.dossier import import_one_dossier_from_ds


class Command(BaseCommand):
    """
    Usage:
        python manage.py ds_import_dossier <dossier_number>

    Example:
        python manage.py ds_import_dossier 123456
    """

    help = (
        "Importe un dossier depuis DN si sa démarche est présente sur Turgot "
        "et s'il n'existe pas déjà"
    )

    def add_arguments(self, parser):
        parser.add_argument("dossier_number", type=int, help="Numéro du dossier sur DN")

    def handle(self, *args, **options):
        dossier_number = options["dossier_number"]
        self.stdout.write(f"Récupération du dossier #{dossier_number} depuis DN…")
        import_one_dossier_from_ds(dossier_number)
        self.stdout.write(self.style.SUCCESS("Terminé."))

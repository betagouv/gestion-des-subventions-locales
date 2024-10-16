from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.importer.dossier import save_demarche_dossiers_from_ds


class Command(BaseCommand):
    help = "Save all dossiers from a previously saved demarche"

    def add_arguments(self, parser):
        parser.add_argument("demarche_number", type=int)

    def handle(self, *args, **options):
        save_demarche_dossiers_from_ds(options["demarche_number"])

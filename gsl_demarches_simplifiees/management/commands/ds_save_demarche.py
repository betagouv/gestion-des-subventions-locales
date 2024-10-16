from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.importer.demarche import save_demarche_from_ds


class Command(BaseCommand):
    help = "Get info about one demarche from its number"

    def add_arguments(self, parser):
        parser.add_argument("demarche_number", type=int)

    def handle(self, *args, **options):
        save_demarche_from_ds(options["demarche_number"])

from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.ds_client import DsClient


class Command(BaseCommand):
    help = "Get info about one demarche from its number"

    def add_arguments(self, parser):
        parser.add_argument("dossier_number", type=int)

    def handle(self, *args, **options):
        client = DsClient()
        print(client.get_one_dossier(options["dossier_number"]))

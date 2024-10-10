from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.ds_client import DsClient


class Command(BaseCommand):
    help = "Get info about one demarche from its number"

    def add_arguments(self, parser):
        parser.add_argument("demarche_number", type=int)

    def handle(self, *args, **options):
        client = DsClient()
        print("===== démarches : =======")
        print(client.get_demarche(options["demarche_number"]))
        print("===== dossiers : ========")
        for dossier in client.get_demarche_dossiers(options["demarche_number"]):
            print(dossier)
            print("-" * 30)

from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.ds_client import DsClient


class Command(BaseCommand):
    help = "Get info about one demarche from its number"

    def add_arguments(self, parser):
        parser.add_argument("demarche_number", type=int)

    def handle(self, *args, **options):
        client = DsClient()
        for index, dossier in enumerate(
            client.get_demarche_dossiers(options["demarche_number"])
        ):
            print(f"----- #{index} -----")
            print(dossier)

        message = f"Total: {index+1} dossier(s)"
        print("=" * len(message))
        print(message)
        print("=" * len(message))

import mimetypes
from datetime import datetime
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from gsl_demarches_simplifiees.ds_client import DsClient, DsMutator


class Command(BaseCommand):
    help = "Test-only: upload a file to Démarches Simplifiées using DsMutator._upload_attachment and print the blob id."

    def add_arguments(self, parser):
        parser.add_argument(
            "dossier_number", type=int, help="Dossier number to attach the file to"
        )
        parser.add_argument(
            "file_path", type=str, help="Path to the file to upload (must be a PDF)"
        )

    def handle(self, *args, **options):
        dossier_number: int = options["dossier_number"]
        ds_client = DsClient()
        dossier = ds_client.get_one_dossier(dossier_number)
        dossier_id = dossier["id"]
        file_path = Path(options["file_path"]).expanduser().resolve()

        if not file_path.exists() or not file_path.is_file():
            raise CommandError(f"File not found: {file_path}")

        # Guess content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type != "application/pdf":
            raise CommandError(f"File is not a PDF: {file_path}")

        # Prepare a Django UploadedFile compatible object
        filename_date = datetime.now().strftime("%Y%m%d-%H%M%S")
        uploaded = SimpleUploadedFile(
            name=f"test_upload_{filename_date}.pdf",
            content=file_path.read_bytes(),
            content_type=content_type,
        )

        mutator = DsMutator()
        blob_id = mutator._upload_attachment(dossier_id, uploaded)

        self.stdout.write(self.style.SUCCESS(f"Uploaded. signedBlobId: {blob_id}"))

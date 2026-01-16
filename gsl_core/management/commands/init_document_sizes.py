# app/management/commands/init_document_sizes.py
# This command is used to initialize the size of the documents that were not generated yet.
# It will be used once the migration 0014_arrete_size_lettrenotification_size is applied.
# We can remove it once the migration is applied.

from django.core.management.base import BaseCommand

from gsl_notification.models import Arrete, LettreNotification
from gsl_notification.utils import generate_pdf_for_generated_document


class Command(BaseCommand):
    help = "Initialise la taille des documents existants"

    def handle(self, *args, **options):
        for model in (Arrete, LettreNotification):
            qs = model.objects.filter(size__isnull=True)
            for doc in qs.iterator():
                pdf_bytes = generate_pdf_for_generated_document(doc)
                doc.size = len(pdf_bytes)
                doc.save(update_fields=["size"])

        self.stdout.write(self.style.SUCCESS("Tailles initialisées"))

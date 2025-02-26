import logging

from django.core.management.base import BaseCommand

from gsl_core.models import Arrondissement, Perimetre


class Command(BaseCommand):
    """
    python manage.py create_perimetres
    """

    help = "Create all perimeters from existing territoires"

    def handle(self, *args, **kwargs):
        i = 0
        for arrondissement in Arrondissement.objects.select_related(
            "departement", "departement__region"
        ).all():
            _, is_created = Perimetre.objects.get_or_create(
                arrondissement=arrondissement,
                departement=arrondissement.departement,
                region=arrondissement.departement.region,
            )
            if is_created:
                i += 1

            _, is_created = Perimetre.objects.get_or_create(
                arrondissement=None,
                departement=arrondissement.departement,
                region=arrondissement.departement.region,
            )
            if is_created:
                i += 1

            _, is_created = Perimetre.objects.get_or_create(
                arrondissement=None,
                departement=None,
                region=arrondissement.departement.region,
            )
            if is_created:
                i += 1

        logging.info(f"Et voilà le travail, {i} périmètres ont été créés")

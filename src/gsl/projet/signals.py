from django.dispatch import receiver

from gsl.chorus.signals import suivi_financier_imported

from .models import EnveloppeProjet


@receiver(suivi_financier_imported)
def fill_ej_from_chorus(sender, **kwargs):
    EnveloppeProjet.objects.fill_empty_ej_from_chorus()

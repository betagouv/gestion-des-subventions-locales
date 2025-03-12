import re

from django.contrib import messages

from gsl_core.templatetags.gsl_filters import euro
from gsl_simulation.models import SimulationProjet


def replace_comma_by_dot(value: str | None) -> float | None:
    """
    Convert a string with spaces and commas to a float.
    Example: "10 000 ,00" -> 10000.00
    """
    if value is None:
        return None

    # Remove all spaces
    value = re.sub(r"\s+", "", value)

    # Replace comma with dot
    value = value.replace(",", ".")

    try:
        return round(float(value), 2)
    except ValueError:
        return 0.0


def add_success_message(
    request, message_type: str | None, simulation_projet: SimulationProjet
):
    if message_type == SimulationProjet.STATUS_REFUSED:
        messages.info(
            request,
            "Le financement de ce projet vient d’être refusé.",
            extra_tags=message_type,
        )
    if message_type == SimulationProjet.STATUS_ACCEPTED:
        messages.info(
            request,
            f"Le financement de ce projet vient d’être accepté avec la dotation {simulation_projet.enveloppe.type} pour {euro(simulation_projet.montant, 2)}.",
            extra_tags=message_type,
        )
    if message_type == SimulationProjet.STATUS_PROVISOIRE:
        messages.info(
            request,
            "Le projet est accepté provisoirement dans cette simulation.",
            extra_tags=message_type,
        )
    if message_type == SimulationProjet.STATUS_DISMISSED:
        messages.info(
            request,
            "Le projet est classé sans suite.",
            extra_tags=message_type,
        )

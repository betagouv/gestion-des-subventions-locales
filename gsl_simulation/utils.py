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
    STATUS_TO_MESSAGE = {
        SimulationProjet.STATUS_REFUSED: "Le financement de ce projet vient d’être refusé.",
        SimulationProjet.STATUS_ACCEPTED: f"Le financement de ce projet vient d’être accepté avec la dotation {simulation_projet.enveloppe.dotation} pour {euro(simulation_projet.montant, 2)}.",
        SimulationProjet.STATUS_DISMISSED: "Le projet est classé sans suite.",
        SimulationProjet.STATUS_PROVISOIRE: "Le projet est accepté provisoirement dans cette simulation.",
        SimulationProjet.STATUS_PROCESSING: "Le projet est revenu en traitement.",
    }
    if message_type in STATUS_TO_MESSAGE:
        messages.info(
            request,
            STATUS_TO_MESSAGE[message_type],
            extra_tags=message_type,
        )

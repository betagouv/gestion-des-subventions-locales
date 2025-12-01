from django import template
from django.urls import reverse

from gsl_simulation.models import SimulationProjet

register = template.Library()


SIMULATION_ONLY_STATUS = [
    SimulationProjet.STATUS_PROCESSING,
    SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
    SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
]


@register.filter(name="status_url")
def status_url(simulation: SimulationProjet, status):
    if status == SimulationProjet.STATUS_REFUSED:
        return reverse("gsl_simulation:refuse-form", kwargs={"pk": simulation.pk})
    if status == SimulationProjet.STATUS_DISMISSED:
        return reverse(
            "gsl_simulation:dismiss-form",
            kwargs={"pk": simulation.pk},
        )

    return reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": simulation.pk, "status": status},
    )


@register.filter(name="status_needs_modal")
def status_needs_modal(simulation_projet: SimulationProjet, status):
    """
    Discriminate between status that needs a confirmation modal (GET) and those that don't (POST).
    """
    return (
        status not in SIMULATION_ONLY_STATUS
        or simulation_projet.status not in SIMULATION_ONLY_STATUS
    )


@register.filter(name="status_to_french_word")
def status_to_french_word(status):
    return {
        SimulationProjet.STATUS_ACCEPTED: "validé",
        SimulationProjet.STATUS_REFUSED: "refusé",
        SimulationProjet.STATUS_DISMISSED: "classé sans suite",
    }[status]

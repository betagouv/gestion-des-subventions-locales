from django import template
from django.urls import reverse

from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_simulation.models import SimulationProjet

register = template.Library()


@register.filter(name="status_url")
def status_url(simulation: SimulationProjet, status):
    if status in SimulationProjet.SIMULATION_PENDING_STATUSES:
        return reverse(
            "simulation:simulation-projet-update-simulation-status",
            kwargs={"pk": simulation.pk, "status": status},
        )

    return reverse(
        "simulation:simulation-projet-update-programmed-status",
        kwargs={"pk": simulation.pk, "status": status},
    )


@register.filter(name="status_needs_modal")
def status_needs_modal(simulation_projet: SimulationProjet, status):
    """
    Discriminate between status that needs a confirmation modal (GET) and those that don't (POST).

    Could also be named `status_change_affects_programmation`
    """
    return (
        status not in SimulationProjet.SIMULATION_PENDING_STATUSES
        or simulation_projet.status not in SimulationProjet.SIMULATION_PENDING_STATUSES
    )


@register.filter(name="status_to_adjective")
def status_to_adjective(status, feminine=False):
    return {
        SimulationProjet.STATUS_PROVISIONALLY_REFUSED: f"refusé{'e' if feminine else ''} provisoirement",
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: f"accepté{'e' if feminine else ''} provisoirement",
        SimulationProjet.STATUS_PROCESSING: "en traitement",
        SimulationProjet.STATUS_ACCEPTED: f"validé{'e' if feminine else ''}",
        PROJET_STATUS_REFUSED: f"refusé{'e' if feminine else ''}",
        SimulationProjet.STATUS_REFUSED: f"refusé{'e' if feminine else ''}",
        SimulationProjet.STATUS_DISMISSED: f"classé{'e' if feminine else ''} sans suite",
    }[status]


@register.filter(name="status_to_action_word")
def status_to_action_word(status):
    return {
        PROJET_STATUS_ACCEPTED: "accepter",
        SimulationProjet.STATUS_ACCEPTED: "accepter",
        SimulationProjet.STATUS_PROVISIONALLY_REFUSED: "refuser provisoirement",
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: "accepter provisoirement",
        SimulationProjet.STATUS_PROCESSING: "remettre en traitement",
        PROJET_STATUS_REFUSED: "refuser",
        SimulationProjet.STATUS_REFUSED: "refuser",
        SimulationProjet.STATUS_DISMISSED: "classer sans suite",
    }[status]


@register.filter(name="status_to_label")
def status_to_label(status):
    return dict(SimulationProjet.STATUS_CHOICES)[status]


@register.filter(name="status_to_fr_color")
def status_to_fr_color(status):
    return {
        SimulationProjet.STATUS_ACCEPTED: "success",
        PROJET_STATUS_REFUSED: "error",
        SimulationProjet.STATUS_REFUSED: "error",
        PROJET_STATUS_DISMISSED: "warning",
        SimulationProjet.STATUS_DISMISSED: "warning",
    }[status]


@register.filter(name="split_symbol_and_status")
def split_symbol_and_status(symbol_and_status):
    symbol = symbol_and_status[0]
    status = symbol_and_status[2:]
    return f"<span aria-hidden='true'>{symbol}</span> {status}"

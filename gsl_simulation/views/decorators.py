import logging

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_simulation.models import Simulation, SimulationProjet


def simulation_projet_must_be_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        check_if_simulation_projet_enveloppe_is_in_user_enveloppes(user, kwargs["pk"])
        return func(*args, **kwargs)

    return wrapper


def check_if_simulation_projet_enveloppe_is_in_user_enveloppes(
    user, simulation_projet_id
):
    if user.is_staff:
        return

    simulation_projet = get_object_or_404(SimulationProjet, id=simulation_projet_id)
    enveloppes_visible_by_user = EnveloppeService.get_enveloppes_visible_for_a_user(
        user
    )
    if simulation_projet.simulation.enveloppe not in enveloppes_visible_by_user:
        raise Http404("No %s matches the given query." % Simulation._meta.object_name)


def simulation_must_be_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        simulation = get_object_or_404(Simulation, slug=kwargs["slug"])
        enveloppes_visible_by_user = EnveloppeService.get_enveloppes_visible_for_a_user(
            user
        )
        if simulation.enveloppe not in enveloppes_visible_by_user:
            raise Http404(
                "No %s matches the given query." % Simulation._meta.object_name
            )

        return func(*args, **kwargs)

    return wrapper


def projet_must_be_in_user_perimetre(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        simulation_projet = get_object_or_404(SimulationProjet, id=kwargs["pk"])
        enveloppe = simulation_projet.simulation.enveloppe
        enveloppes_visible_by_user = EnveloppeService.get_enveloppes_visible_for_a_user(
            user
        )
        if enveloppe not in enveloppes_visible_by_user:
            raise Http404(
                "No %s matches the given query." % SimulationProjet._meta.object_name
            )

        return func(*args, **kwargs)

    return wrapper


def exception_handler_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Http404 as e:
            logging.info("An error occurred: %s", str(e), exc_info=True)
            return JsonResponse(
                {
                    "error": "Not found.",
                },
                status=404,
            )
        except Exception as e:
            logging.error("An error occurred: %s", str(e), exc_info=True)
            return JsonResponse(
                {
                    "error": "An internal error has occurred.",
                },
                status=500,
            )

    return wrapper

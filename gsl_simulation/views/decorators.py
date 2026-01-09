import logging

from django.http import Http404 as DjangoHttp404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from gsl_core.exceptions import Http404
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_simulation.models import Simulation

logger = logging.getLogger(__name__)


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
            raise Http404(user_message="Simulation non trouvée")

        return func(*args, **kwargs)

    return wrapper


def exception_handler_decorator(func):
    # TODO : merge this with django error handlers settings
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (Http404, DjangoHttp404) as e:
            logger.info("404 Error: %s", str(e), exc_info=True)
            return JsonResponse(
                {
                    "error": "Not found.",
                },
                status=404,
            )
        except Exception as e:
            logger.exception("500 Error: %s", str(e))
            return JsonResponse(
                {
                    "error": "An internal error has occurred.",
                },
                status=500,
            )

    return wrapper

import logging

from django.shortcuts import get_object_or_404

from gsl_core.exceptions import Http404
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_simulation.models import Simulation

logger = logging.getLogger(__name__)


# TODO delete this ! replace by get_queryset in CBV
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

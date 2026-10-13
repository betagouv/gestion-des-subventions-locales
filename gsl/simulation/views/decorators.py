import logging

from django.shortcuts import get_object_or_404

from gsl.core.exceptions import Http404
from gsl.programmation.models import Enveloppe

from ..models import Simulation

logger = logging.getLogger(__name__)


# TODO delete this ! replace by get_queryset in CBV
def simulation_must_be_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        simulation = get_object_or_404(Simulation, slug=kwargs["slug"])
        enveloppes_visible_by_user = Enveloppe.objects.for_user(
            user, staff_can_access_to_all=True
        )
        if simulation.enveloppe not in enveloppes_visible_by_user:
            raise Http404(user_message="Simulation non trouvée")

        return func(*args, **kwargs)

    return wrapper

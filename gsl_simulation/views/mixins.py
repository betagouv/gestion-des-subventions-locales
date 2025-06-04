from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy

from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_simulation.models import SimulationProjet


class CorrectUserPerimeterRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        simulation_projet = get_object_or_404(
            SimulationProjet, id=self.request.resolver_match.kwargs["pk"]
        )
        enveloppes_visible_by_user = EnveloppeService.get_enveloppes_visible_for_a_user(
            user
        )
        return simulation_projet.enveloppe in enveloppes_visible_by_user

    def handle_no_permission(self):
        return HttpResponseRedirect(reverse_lazy("simulation:simulation-list"))

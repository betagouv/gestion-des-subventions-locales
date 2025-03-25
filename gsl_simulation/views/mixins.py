from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy

from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_simulation.models import SimulationProjet

"""
UserPassesTestMixin cannot be stacked
https://docs.djangoproject.com/en/4.0/topics/auth/default/#django.contrib.auth.mixins.UserPassesTestMixin.get_test_func
https://stackoverflow.com/a/60302594/4293684

How to have LoginRequiredMixin (redirects to next url if anonymous) + custom mixin ?
--> custom dispatch() method
"""


class LoginRequiredUserPassesTestMixin(UserPassesTestMixin):
    """
    Custom mixin that mimicks the LoginRequiredMixin behavior
    https://stackoverflow.com/a/59661739
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().dispatch(request, *args, **kwargs)


class CorrectUserPerimeterRequiredMixin(LoginRequiredUserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        simulation_projet = get_object_or_404(
            SimulationProjet, id=self.request.resolver_match.kwargs["pk"]
        )
        enveloppes_visible_by_user = EnveloppeService.get_enveloppes_visible_for_a_user(
            user
        )
        return simulation_projet.simulation.enveloppe in enveloppes_visible_by_user

    def handle_no_permission(self):
        return HttpResponseRedirect(reverse_lazy("simulation:simulation-list"))

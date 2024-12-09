from django.views.generic.detail import DetailView

from .models import Scenario, SimulationProjet


class ScenarioDetailView(DetailView):
    model = Scenario

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["simulations"] = SimulationProjet.objects.filter(
            scenario=self.get_object()
        )
        return context

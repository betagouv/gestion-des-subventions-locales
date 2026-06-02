from gsl_simulation.views.simulation_projet_views import SimulationProjetDetailView


class SimulationProjetHistoriqueView(SimulationProjetDetailView):
    template_name = "gsl_simulation/tab_simulation_projet/tab_historique.html"

    def get_queryset(self):
        return super().get_queryset().in_user_perimeter(self.request.user)

    def get_template_names(self):
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            with_specific_info_for_main_tab=False, **kwargs
        )
        context["actions"] = self.object.projet.actions.select_related(
            "actor"
        ).order_by("-created_at")
        return context

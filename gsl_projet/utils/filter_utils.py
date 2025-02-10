class FilterUtils:
    FILTER_TEMPLATE_MAPPINGS = {
        "dotation": "includes/_filter_dotation.html",
        "porteur": "includes/_filter_porteur.html",
        "status": "includes/_filter_status.html",
        "cout_total": "includes/_filter_cout_total.html",
        "montant_demande": "includes/_filter_montant_demande.html",
        "montant_retenu": "includes/_filter_montant_retenu.html",
    }

    def enrich_context_with_filter_utils(self, context, state_mappings):
        context["is_status_active"] = self._get_is_one_field_active(["status"])
        context["is_status_placeholder"] = self._get_status_placeholder(state_mappings)
        context["is_cout_total_active"] = self._get_is_one_field_active(
            ["cout_min", "cout_max"]
        )
        context["is_montant_demande_active"] = self._get_is_one_field_active(
            ["montant_demande_min", "montant_demande_max"]
        )
        context["is_montant_retenu_active"] = self._get_is_one_field_active(
            ["montant_retenu_min", "montant_retenu_max"]
        )

        context["filter_templates"] = self._get_filter_templates()

        return context

    def _get_filter_templates(self):
        try:
            filters = self.get_filterset(self.filterset_class).filterset
            return (self.FILTER_TEMPLATE_MAPPINGS[filter] for filter in filters)
        except AttributeError:  # no filterset => we display all filters
            return self.FILTER_TEMPLATE_MAPPINGS.values()

    def _get_status_placeholder(self, state_mappings):
        if self.request.GET.get("status") in (None, "", []):
            return "Tous"
        return ", ".join(
            [state_mappings[status] for status in self.request.GET.getlist("status")]
        )

    def _get_is_one_field_active(self, field_names):
        for field_name in field_names:
            if self.request.GET.get(field_name) not in (None, ""):
                return True
        return False

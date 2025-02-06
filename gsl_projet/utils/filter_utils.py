from gsl_demarches_simplifiees.models import Dossier


class FilterUtils:
    DS_STATE_MAPPINGS = {key: value for key, value in Dossier.DS_STATE_VALUES}

    def enrich_context_with_filter_utils(self, context):
        context["is_status_active"] = self._get_is_one_field_active(["status"])
        context["is_status_placeholder"] = self._get_status_placeholder()
        context["is_cout_total_active"] = self._get_is_one_field_active(
            ["cout_min", "cout_max"]
        )
        context["is_montant_demande_active"] = self._get_is_one_field_active(
            ["montant_demande_min", "montant_demande_max"]
        )
        context["is_montant_retenu_active"] = self._get_is_one_field_active(
            ["montant_retenu_min", "montant_retenu_max"]
        )

        return context

    def _get_status_placeholder(self):
        if self.request.GET.get("status") in (None, "", []):
            return "Tous"
        return ", ".join(
            [
                self.DS_STATE_MAPPINGS[status]
                for status in self.request.GET.getlist("status")
            ]
        )

    def _get_is_one_field_active(self, field_names):
        for field_name in field_names:
            if self.request.GET.get(field_name) not in (None, ""):
                return True
        return False

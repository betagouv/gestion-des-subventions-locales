from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_projet.utils.projet_filters import ProjetFilters


class FilterUtils:
    FILTER_TEMPLATE_MAPPINGS = {
        "dotation": "includes/_filter_dotation.html",
        "porteur": "includes/_filter_porteur.html",
        "status": "includes/_filter_status.html",
        "cout_total": "includes/_filter_cout_total.html",
        "montant_demande": "includes/_filter_montant_demande.html",
        "montant_retenu": "includes/_filter_montant_retenu.html",
        "montant_previsionnel": "includes/_filter_montant_previsionnel.html",
        "territoire": "includes/_filter_territoire.html",
    }

    DOTATION_MAPPING = dict(ProjetFilters.DOTATION_CHOICES)
    PORTEUR_MAPPING = dict(NaturePorteurProjet.TYPE_CHOICES)

    def enrich_context_with_filter_utils(self, context, state_mappings):
        context["is_dotation_active"] = self._get_is_one_field_active("dotation")
        context["dotation_placeholder"] = self._get_dotation_placeholder()
        context["is_status_active"] = self._get_is_one_field_active("status")
        context["status_placeholder"] = self._get_status_placeholder(state_mappings)
        context["is_cout_total_active"] = self._get_is_one_field_active(
            "cout_min", "cout_max"
        )
        context["is_montant_demande_active"] = self._get_is_one_field_active(
            "montant_demande_min", "montant_demande_max"
        )
        context["is_montant_retenu_active"] = self._get_is_one_field_active(
            "montant_retenu_min", "montant_retenu_max"
        )
        context["is_montant_previsionnel_active"] = self._get_is_one_field_active(
            "montant_previsionnel_min", "montant_previsionnel_max"
        )
        context["is_porteur_active"] = self._get_is_one_field_active("porteur")
        context["porteur_placeholder"] = self._get_porteur_placeholder()
        context["is_territoire_active"] = self._get_is_one_field_active("territoire")
        context["territoire_placeholder"], context["territoire_selected"] = (
            self._get_selected_territoires()
        )
        context["territoire_choices"] = self._get_territoire_choices()
        context["filter_templates"] = self._get_filter_templates()

        return context

    def _get_dotation_placeholder(self):
        if self.request.GET.getlist("dotation") in ("", None, []):
            return "Toutes les dotations"

        return ", ".join(
            FilterUtils.DOTATION_MAPPING[dotation]
            for dotation in self.request.GET.getlist("dotation")
            if dotation in FilterUtils.DOTATION_MAPPING
        )

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
            state_mappings[status]
            for status in self.request.GET.getlist("status")
            if status in state_mappings
        )

    def _get_porteur_placeholder(self):
        if self.request.GET.getlist("porteur") in (None, "", []):
            return "Tous"
        return ", ".join(
            FilterUtils.PORTEUR_MAPPING[porteur]
            for porteur in self.request.GET.getlist("porteur")
        )

    def _get_selected_territoires(self):
        view_perimetre = self._get_perimetre()
        if self.request.GET.get("territoire") in (None, "", []):
            label = view_perimetre.entity_name if view_perimetre else "Tous"
            return label, set()

        territoire_ids = set(
            int(perimetre) for perimetre in self.request.GET.getlist("territoire")
        )
        perimetres = Perimetre.objects.filter(id__in=territoire_ids).select_related(
            "departement", "region", "arrondissement"
        )
        return ", ".join(p.entity_name for p in perimetres), territoire_ids

    def _get_perimetre(self) -> Perimetre:
        raise NotImplementedError

    def _get_territoire_choices(self):
        raise NotImplementedError

    def _get_is_one_field_active(self, *field_names):
        return any(
            self.request.GET.get(field_name) not in (None, "")
            for field_name in field_names
        )

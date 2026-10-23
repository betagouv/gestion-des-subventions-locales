import json
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.views.generic import TemplateView

from gsl.core.models import Commune


class CollectiviteFicoView(TemplateView):
    template_name = "gsl_stats/collectivite_fico.html"
    components = "identite,programmes,financements.*"

    def get(self, request, *args, **kwargs):
        choisie = request.GET.get("siren")
        if choisie:
            return redirect("suivi_financier:collectivite-fico", choisie)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        siren = self.kwargs.get("siren")
        perimetre = getattr(self.request.user, "perimetre", None)
        context = {
            "title": "Fiche collectivité" if siren else "Fiches collectivités",
            "perimetre": perimetre,
            "fico_url": settings.FICO_URL,
        }
        if perimetre:
            context["geo_api_query"] = (
                f"codeDepartement={perimetre.departement_id}"
                if perimetre.departement_id
                else f"codeRegion={perimetre.region_id}"
            )
        if perimetre and perimetre.arrondissement_id:
            insee_codes = Commune.objects.filter(
                arrondissement=perimetre.arrondissement
            ).values_list("insee_code", flat=True)
            context["arrondissement_communes"] = json.dumps(list(insee_codes))
        if siren:
            query = urlencode({"component": self.components})
            context["pdf_url"] = f"{settings.FICO_URL}/fiches/{siren}.pdf?{query}"
        return super().get_context_data(**context, **kwargs)

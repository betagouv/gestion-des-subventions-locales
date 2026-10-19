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
        collectivites = (
            Commune.objects.exclude(siren="").for_perimetre(perimetre).order_by("name")
            if perimetre
            else Commune.objects.none()
        )
        context = {
            "title": "Fiche collectivité" if siren else "Fiches collectivités",
            "collectivites": collectivites,
            "dans_perimetre": any(c.siren == siren for c in collectivites),
            "fico_url": settings.FICO_URL,
        }
        if siren:
            query = urlencode({"component": self.components})
            context["pdf_url"] = f"{settings.FICO_URL}/fiches/{siren}.pdf?{query}"
        return super().get_context_data(**context, **kwargs)

from django.conf import settings
from django.db.models import Case, Value, When
from django.shortcuts import redirect
from django.views.generic import TemplateView

from gsl.core.models import Perimetre
from gsl_demarches_simplifiees.models import PersonneMorale


def _personnes_morales_du_perimetre(perimetre: Perimetre | None):
    qs = PersonneMorale.objects.all()
    if perimetre is None:
        return qs.none()
    if perimetre.arrondissement:
        return qs.filter(address__commune__arrondissement=perimetre.arrondissement)
    if perimetre.departement:
        return qs.filter(address__commune__departement=perimetre.departement)
    if perimetre.region:
        return qs.filter(address__commune__departement__region=perimetre.region)
    return qs.none()


class CollectiviteFicoView(TemplateView):
    template_name = "gsl_stats/collectivite_fico.html"
    components = "identite,programmes,carto,chiffres,historique"

    def get(self, request, *args, **kwargs):
        choisie = request.GET.get("siren")
        if choisie:
            return redirect("suivi_financier:collectivite-fico", choisie)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        siren = self.kwargs.get("siren")
        collectivites = (
            _personnes_morales_du_perimetre(
                getattr(self.request.user, "perimetre", None)
            )
            .exclude(siren="")
            .distinct_by_siren()
            .order_by(
                Case(When(raison_sociale="", then=Value(1)), default=Value(0)),
                "raison_sociale",
            )
        )
        context = {
            "title": "Fiche collectivité" if siren else "Fiches collectivités",
            "collectivites": collectivites,
            "dans_perimetre": any(c.siren == siren for c in collectivites),
            "fico_url": settings.FICO_URL,
        }
        if siren:
            fiche_url = f"{settings.FICO_URL}/fiches/{siren}"
            query = f"component={self.components}"
            context["fiche_src"] = f"{fiche_url}.json?{query}"
            context["pdf_url"] = f"{fiche_url}.pdf?{query}"
        return super().get_context_data(**context, **kwargs)

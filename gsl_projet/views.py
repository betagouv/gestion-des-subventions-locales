from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from django.views.generic import ListView
from django_filters.views import FilterView

from gsl_projet.services import ProjetService
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.projet_filters import ProjetFilters
from gsl_projet.utils.projet_page import PROJET_MENU

from .models import Projet


def visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        projet = get_object_or_404(Projet, id=kwargs["projet_id"])
        is_projet_visible_by_user = (
            Projet.objects.for_user(user).filter(id=projet.id).exists()
        )
        if not is_projet_visible_by_user:
            raise Http404("No %s matches the given query." % Projet._meta.object_name)

        return func(*args, **kwargs)

    return wrapper


@visible_by_user
@require_GET
def get_projet(request, projet_id):
    projet = get_object_or_404(Projet, id=projet_id)
    title = projet.dossier_ds.projet_intitule
    context = {
        "title": title,
        "projet": projet,
        "dossier": projet.dossier_ds,
        "breadcrumb_dict": {
            "current": title,
        },
        "menu_dict": PROJET_MENU,
    }
    return render(request, "gsl_projet/projet.html", context)


class ProjetListViewFilters(ProjetFilters):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )

    filterset = (
        "territoire",
        "porteur",
        "dotation",
        "status",
        "cout_total",
        "montant_demande",
        "montant_retenu",
    )

    @property
    def qs(self):
        qs = super().qs
        qs = qs.for_user(self.request.user)
        qs = qs.for_current_year()
        qs = qs.select_related(
            "address",
            "address__commune",
            "perimetre",
        ).prefetch_related(
            "dossier_ds__demande_eligibilite_detr",
            "dossier_ds__demande_eligibilite_dsil",
        )
        return qs


class ProjetListView(FilterView, ListView, FilterUtils):
    model = Projet
    paginate_by = 25
    filterset_class = ProjetListViewFilters
    template_name = "gsl_projet/projet_list.html"
    STATE_MAPPINGS = {key: value for key, value in Projet.STATUS_CHOICES}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = context["object_list"]
        context["title"] = "Projets 2025"
        context["porteur_mappings"] = ProjetService.PORTEUR_MAPPINGS
        context["breadcrumb_dict"] = {}
        context["total_cost"] = ProjetService.get_total_cost(qs)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs)
        context["total_amount_granted"] = 0  # TODO
        self.enrich_context_with_filter_utils(context, self.STATE_MAPPINGS)

        return context

    def _get_perimetre(self):
        if hasattr(self.request, "user") and self.request.user.perimetre:
            return self.request.user.perimetre

    def _get_territoire_choices(self):
        perimetre = self._get_perimetre()
        if not perimetre:
            return ()

        return (perimetre, *perimetre.children())

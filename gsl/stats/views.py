from django.db.models import Case, Q, Value, When
from django.http import Http404
from django.shortcuts import render
from django.views import View
from django.views.generic import ListView

from gsl.projet.models import Projet
from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import PersonneMorale

from .models import Subvention


class CollectiviteListView(ListView):
    model = PersonneMorale
    template_name = "gsl_stats/collectivite_list.html"
    context_object_name = "collectivites"
    paginate_by = 50

    def get_queryset(self):
        qs = _personnes_morales_in_perimetre(self.request.user)
        qs = qs.exclude(siren="")

        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(raison_sociale__icontains=search) | Q(siren__icontains=search)
            )

        qs = qs.distinct_by_siren().select_related("forme_juridique")

        return qs.order_by(
            Case(When(raison_sociale="", then=Value(1)), default=Value(0)),
            "raison_sociale",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["title"] = "Collectivités"
        return context


class CollectiviteDetailView(View):
    template_name = "gsl_stats/collectivite_detail.html"

    def get(self, request, siren):
        personne_morale = (
            _personnes_morales_in_perimetre(request.user).filter(siren=siren).first()
        )
        if personne_morale is None:
            raise Http404("Collectivité introuvable")

        subventions = Subvention.objects.filter(siren=siren).select_related(
            "departement", "commune"
        )
        subventions = subventions.order_by("-exercice", "dispositif")

        if request.user.is_staff:
            projets = Projet.objects.filter(dossier_ds__ds_demandeur__siren=siren)
        else:
            projets = Projet.objects.for_user(request.user).filter(
                dossier_ds__ds_demandeur__siren=siren
            )
        projets = (
            projets.select_related("dossier_ds", "dossier_ds__ds_demandeur")
            .prefetch_related("dotationprojet_set__programmation_projet")
            .order_by("-dossier_ds__ds_date_depot")
        )

        collectivite_nom = personne_morale.nom_affichage
        context = {
            "siren": siren,
            "collectivite_nom": collectivite_nom,
            "subventions": subventions,
            "projets": projets,
            "title": f"Collectivité – {collectivite_nom}",
        }
        return render(request, self.template_name, context)


def _personnes_morales_in_perimetre(user):
    qs = PersonneMorale.objects.all()
    if user.is_staff:
        return qs
    perimetre: Perimetre | None = getattr(user, "perimetre", None)
    if perimetre is None:
        return qs.none()
    if perimetre.arrondissement:
        return qs.filter(address__commune__arrondissement=perimetre.arrondissement)
    if perimetre.departement:
        return qs.filter(address__commune__departement=perimetre.departement)
    if perimetre.region:
        return qs.filter(address__commune__departement__region=perimetre.region)
    return qs.none()

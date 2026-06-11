from django.db.models import Q
from django.views.generic import DetailView, ListView

from gsl_core.models import Perimetre
from gsl_projet.models import Projet

from .models import Beneficiaire


class BeneficiaireListView(ListView):
    model = Beneficiaire
    template_name = "gsl_suivi_financier/beneficiaire_list.html"
    context_object_name = "beneficiaires"
    paginate_by = 50

    def get_queryset(self):
        qs = Beneficiaire.objects.all()
        qs = _filter_by_perimetre(qs, self.request.user)

        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(Q(nom__icontains=search) | Q(siren__icontains=search))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["title"] = "Bénéficiaires"
        return context


class BeneficiaireDetailView(DetailView):
    model = Beneficiaire
    pk_url_kwarg = "siren"
    template_name = "gsl_suivi_financier/beneficiaire_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        beneficiaire = self.object

        subventions = beneficiaire.subventiondgcl_set.select_related(
            "departement", "commune"
        ).order_by("-exercice", "dispositif")

        if self.request.user.is_staff:
            projets = Projet.objects.filter(
                dossier_ds__ds_demandeur__siren=beneficiaire.siren
            )
        else:
            projets = Projet.objects.for_user(self.request.user).filter(
                dossier_ds__ds_demandeur__siren=beneficiaire.siren
            )
        projets = (
            projets.select_related("dossier_ds", "dossier_ds__ds_demandeur")
            .prefetch_related("dotationprojet_set")
            .order_by("-dossier_ds__ds_date_depot")
        )

        context.update(
            {
                "siren": beneficiaire.siren,
                "beneficiaire_nom": beneficiaire.nom,
                "subventions": subventions,
                "projets": projets,
                "title": f"Bénéficiaire – {beneficiaire.nom}",
            }
        )
        return context


def _filter_by_perimetre(qs, user):
    if user.is_staff:
        return qs
    perimetre: Perimetre | None = getattr(user, "perimetre", None)
    if perimetre is None:
        return qs.none()
    if perimetre.arrondissement:
        return qs.filter(
            subventiondgcl__commune__arrondissement=perimetre.arrondissement
        ).distinct()
    if perimetre.departement:
        return qs.filter(subventiondgcl__departement=perimetre.departement).distinct()
    if perimetre.region:
        return qs.filter(
            subventiondgcl__departement__region=perimetre.region
        ).distinct()
    return qs.none()

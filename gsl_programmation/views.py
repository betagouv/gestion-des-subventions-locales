from django.contrib import messages
from django.contrib.auth.views import RedirectURLMixin
from django.db.models import ProtectedError
from django.http import Http404 as DjangoHttp404
from django.shortcuts import redirect
from django.template.defaultfilters import pluralize
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, UpdateView
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django_filters.views import FilterView

from gsl_core.exceptions import Http404
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_CREATION_SOUS_ENVELOPPE,
    MATOMO_CATEGORY_SOUS_ENVELOPPE,
)
from gsl_core.models import Perimetre
from gsl_programmation.forms import SubEnveloppeCreateForm, SubEnveloppeUpdateForm
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_programmation.table_columns import PROGRAMMATION_TABLE_COLUMNS
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
)
from gsl_projet.models import Projet
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_projet.utils.utils import get_comment_cards


class ProgrammationProjetDetailView(DetailView):
    model = Projet
    pk_url_kwarg = "projet_id"
    tab_name = None

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except DjangoHttp404:
            # The Projet may exist but no longer have a ProgrammationProjet
            # (e.g., after a DN refresh reverting the status to processing).
            if (
                Projet.objects.for_user(request.user)
                .filter(pk=kwargs["projet_id"])
                .exists()
            ):
                messages.warning(request, "Ce projet n'est plus en programmation.")
                return redirect("gsl_programmation:programmation-projet-list")
            raise

    def get_template_names(self):
        if self.tab_name:
            return [
                f"gsl_programmation/tab_programmation_projet/tab_{self.tab_name}.html"
            ]
        return ["gsl_programmation/programmation_projet_detail.html"]

    def get_queryset(self):
        return (
            Projet.objects.for_user(self.request.user)
            .with_at_least_one_programmed_dotation()
            .select_related(
                "dossier_ds",
                "dossier_ds__perimetre",
                "dossier_ds__perimetre__departement",
                "demandeur",
            )
            .prefetch_related("dotationprojet_set__detr_categories")
        )

    def get_context_data(self, **kwargs):
        tab = self.tab_name or "projet"
        title = self.object.dossier_ds.projet_intitule
        if "dotation" in self.request.GET:
            try:
                programmation_projet = ProgrammationProjet.objects.get(
                    dotation_projet__projet=self.object,
                    dotation_projet__dotation=self.request.GET["dotation"],
                    dotation_projet__status=PROJET_STATUS_ACCEPTED,
                )
            except ProgrammationProjet.DoesNotExist:
                programmation_projet = ProgrammationProjet.objects.filter(
                    dotation_projet__projet=self.object,
                    dotation_projet__status=PROJET_STATUS_ACCEPTED,
                ).first()
        else:
            programmation_projet = ProgrammationProjet.objects.filter(
                dotation_projet__projet=self.object
            ).first()
        context = {
            "title": title,
            "projet": self.object,
            "dotation_projets": self.object.dotationprojet_set.all(),
            "dossier": self.object.dossier_ds,
            "breadcrumb_dict": {
                "links": [
                    {
                        "url": reverse("gsl_programmation:programmation-projet-list"),
                        "title": "Programmation en cours",
                    },
                ],
                "current": title,
            },
            "menu_dict": PROJET_MENU,
            "current_tab": tab,
            "go_back_link": self.get_go_back_link(),
            "programmation_projet": programmation_projet,
        }
        if tab == "notes":
            context["projet_notes"] = self.object.notes.all()
            context["comment_cards"] = get_comment_cards(self.object)

        return super().get_context_data(**context)

    def get_go_back_link(self):
        url = reverse("gsl_programmation:programmation-projet-list")
        if "dotation" in self.request.GET:
            url = reverse(
                "gsl_programmation:programmation-projet-list-dotation",
                kwargs={"dotation": self.request.GET["dotation"]},
            )
        if self.request.GET.urlencode():
            params = self.request.GET.copy()
            params.pop("dotation", None)

            if params:
                url += "?" + params.urlencode()

        return url


class ProgrammationProjetListView(FilterView, ListView):
    model = ProgrammationProjet
    filterset_class = ProgrammationProjetFilters
    template_name = "gsl_programmation/programmation_projet_list.html"
    context_object_name = "programmation_projets"
    paginate_by = 25
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__demandeur",
                "dotation_projet__projet__dossier_ds",
            )
            .prefetch_related(
                "arrete",
                "lettre_notification",
                "arrete_et_lettre_signes",
                "enveloppe",
                "annexes",
                "enveloppe__perimetre",
                "dotation_projet__projet__dotationprojet_set",
                "dotation_projet__projet__dotationprojet_set__simulationprojet_set",
                "dotation_projet__projet__dotationprojet_set__programmation_projet",
                "dotation_projet__projet__dotationprojet_set__programmation_projet__arrete",
                "dotation_projet__projet__dotationprojet_set__programmation_projet__lettre_notification",
                "dotation_projet__projet__dotationprojet_set__programmation_projet__arrete_et_lettre_signes",
                "dotation_projet__projet__dotationprojet_set__programmation_projet__enveloppe",
                "dotation_projet__projet__dotationprojet_set__programmation_projet__annexes",
                "dotation_projet__projet__dossier_ds__demande_categorie_dsil",
                "dotation_projet__projet__dossier_ds__demande_categorie_detr",
                "dotation_projet__projet__dossier_ds__ds_demarche",
                "dotation_projet__projet__dossier_ds__perimetre",
                "dotation_projet__projet__dossier_ds__porteur_de_projet_arrondissement",
                "dotation_projet__projet__dossier_ds__demande_cofinancements",
                "dotation_projet__projet__dossier_ds__projet_zonage",
                "dotation_projet__projet__dossier_ds__projet_contractualisation",
            )
            .defer("dotation_projet__projet__dossier_ds__ds_demarche__raw_ds_data")
        )

    def get(self, request, *args, **kwargs):
        self.perimetre: Perimetre = self.request.user.perimetre
        self.dotation = kwargs.get("dotation")
        if self.dotation is None:
            return redirect(
                "gsl_programmation:programmation-projet-list-dotation",
                dotation=DOTATION_DETR,
            )
        if self.dotation not in (DOTATION_DETR, DOTATION_DSIL):
            raise Http404(user_message="Dotation non reconnue.")

        if (
            self.dotation == DOTATION_DETR
            and self.perimetre.type == Perimetre.TYPE_REGION
        ):
            return redirect(
                "gsl_programmation:programmation-projet-list-dotation", dotation="DSIL"
            )

        if "reset_filters" in request.GET:
            if request.path.startswith("/programmation/liste/"):
                return redirect(request.path)
            else:
                return redirect("/")

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enveloppe = self.filterset.enveloppe
        title = "Programmation en cours"
        if enveloppe:
            title = f"Programmation {enveloppe.dotation} {enveloppe.annee}"
        context.update(
            {
                "enveloppe": enveloppe,
                "dotation": self.dotation,
                "title": title,
                "to_notify_projets_count": self.object_list.to_notify().count(),
                "activate_all_projets_selection": self.object_list.count()
                > ProgrammationProjetListView.paginate_by,
                "breadcrumb_dict": {
                    "current": "Programmation en cours",
                },
                "current_order": self.request.GET.get("order", ""),
                "columns": PROGRAMMATION_TABLE_COLUMNS,
            }
        )

        if self.perimetre:
            context["territoire_choices"] = (
                self.perimetre,
                *self.perimetre.children(),
            )

        return context


class EnveloppeCreateView(RedirectURLMixin, CreateView):
    model = Enveloppe
    form_class = SubEnveloppeCreateForm
    next_page = reverse_lazy("gsl_projet:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user_perimetre"] = self.request.user.perimetre
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_SOUS_ENVELOPPE,
            MATOMO_ACTION_CREATION_SOUS_ENVELOPPE,
            f"{self.object.dotation} - {self.object.perimetre.type}",
        )
        return response


class EnveloppeUpdateView(UpdateView):
    model = Enveloppe
    form_class = SubEnveloppeUpdateForm
    success_url = reverse_lazy("gsl_projet:list")

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                deleguee_by__isnull=False,
                perimetre__in=(
                    self.request.user.perimetre,
                    *(self.request.user.perimetre.children()),
                ),
            )
        )


@method_decorator(require_POST, name="dispatch")
class EnveloppeDeleteView(DeleteView):
    model = Enveloppe
    success_url = reverse_lazy("gsl_projet:list")

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                deleguee_by__isnull=False,
                perimetre__in=(
                    self.request.user.perimetre,
                    *(self.request.user.perimetre.children()),
                ),
            )
        )

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError as e:
            object_classes = {}
            for obj in e.protected_objects:
                if obj._meta.model_name not in object_classes:
                    object_classes[obj._meta.model_name] = 1
                else:
                    object_classes[obj._meta.model_name] += 1

            objects_count = sum(object_classes.values())
            msgs = []
            if "simulation" in object_classes:
                simulations_count = object_classes["simulation"]
                plural = "s" if simulations_count > 1 else ""
                msgs.append(f"{simulations_count} simulation{plural}")

            if "enveloppe" in object_classes:
                enveloppe_count = object_classes["enveloppe"]
                plural = "s" if enveloppe_count > 1 else ""
                msgs.append(f"{enveloppe_count} enveloppe{plural}")

            messages.error(
                self.request,
                f"Suppression impossible : {' et '.join(msgs)} {pluralize(objects_count, 'est,sont')} rattachée{pluralize(objects_count, 's')} à cette enveloppe.",
            )
            return redirect(self.success_url)

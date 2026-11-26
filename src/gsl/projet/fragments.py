from django.contrib import messages
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django_htmx.http import HttpResponseClientRefresh

from dn.sync.exceptions import DsServiceException
from gsl.core.fragments import Fragment

from .forms import (
    DotationCardForm,
    EnveloppeProjetAssietteForm,
    EnveloppeProjetCreateForm,
    EnveloppeProjetForm,
    ProjetBudgetVertForm,
    ProjetZonageForm,
)
from .models import EnveloppeProjet, Projet


class BaseProjetFragment(Fragment):
    context_object_name = "projet"


class DnActionsFragment(BaseProjetFragment):
    name = "dn_actions"
    template_name = "includes/projet_detail/_dn_actions.html"

    def get_context(self):
        return {
            **super().get_context(),
            "next_url": self.request.htmx.current_url or self.request.path,
        }


class FormFragment(Fragment):
    """Inline edit form rendered by _htmx_fragment_form.html: confirms the save
    with a badge, and treats a form that surfaces errors during save() — e.g. a
    rolled-back Démarches annotation — as invalid."""

    def on_valid(self):
        self.form.save()
        if self.form.errors:
            return self.on_invalid()
        return self.render_valid(saved=True)


class ProjetFormFragment(FormFragment):
    context_object_name = "projet"
    route_params = "<int:pk>"

    @classmethod
    def get_queryset(cls, request):
        return Projet.objects.active().for_user(request.user)

    def get_form(self, data=None):
        return self.form_class(instance=self.object, data=data, user=self.request.user)


class BudgetVertFragment(ProjetFormFragment):
    name = "budget_vert_form"
    form_class = ProjetBudgetVertForm
    template_name = "includes/forms/_is_budget_vert_form.html"


class ZonageFragment(ProjetFormFragment):
    name = "zonage_form"
    form_class = ProjetZonageForm
    template_name = "includes/forms/_boolean_fields_projet_form.html"


class EnveloppeProjetFormFragment(FormFragment):
    context_object_name = "enveloppe_projet"
    route_params = "<int:pk>"

    @classmethod
    def get_queryset(cls, request):
        return EnveloppeProjet.objects.filter(
            projet__in=Projet.objects.active().for_user(request.user)
        )


class DetrAvisCommissionFragment(EnveloppeProjetFormFragment):
    name = "detr_avis_commission_form"
    form_class = EnveloppeProjetForm
    template_name = "includes/forms/_detr_avis_commission_form.html"


class AssietteDotationFragment(EnveloppeProjetFormFragment):
    name = "assiette_dotation_form"
    form_class = EnveloppeProjetAssietteForm
    template_name = "includes/forms/_assiette_enveloppe_projet_form.html"

    @classmethod
    def get_queryset(cls, request):
        return super().get_queryset(request).filter(notified_at__isnull=True)


class DotationCardFragment(EnveloppeProjetFormFragment):
    name = "dotation_card_form"
    form_class = DotationCardForm
    template_name = "includes/forms/_dotation_card_form.html"

    def get_form(self, data=None):
        return self.form_class(instance=self.object, data=data, user=self.request.user)

    def on_get(self):
        """Read-only by default; `?edit` opens the form, and dropping it cancels."""
        editing = "edit" in self.request.GET
        if editing:
            self.form = self.get_form()
            # On the checked year: an autofocus on the radio widget would land on
            # every one of its buttons.
            self.form.fields["annee"].widget.focus_checked = True
        return HttpResponse(self.render(editing=editing))

    def on_valid(self):
        """Back to read-only once saved, displaying the saved values. A new campagne
        changes the card title, the cards order and the other tabs: reload."""
        self.form.save()
        if self.form.errors:
            return self.on_invalid()
        if self.form.annee_changed:
            messages.success(
                self.request,
                f"La dotation {self.object.dotation} est passée sur la campagne "
                f"{self.object.enveloppe.annee}.",
            )
            return HttpResponseClientRefresh()
        self.form = None
        return self.render_valid(saved=True)

    def render_invalid(self):
        return HttpResponse(self.render(editing=True))


class NewDotationCardFragment(BaseProjetFragment):
    """The card of a dotation being added, opened from the « Ajouter une
    dotation » dropdown of the dotations tab with `?choix=<dotation>-<annee>`.
    Without a choice, it renders empty: that is how the card is cancelled."""

    name = "new_dotation_card"
    route_params = "<int:pk>"
    form_class = EnveloppeProjetCreateForm
    template_name = "includes/forms/_new_dotation_card.html"

    @classmethod
    def get_queryset(cls, request):
        return Projet.objects.active().for_user(request.user)

    @cached_property
    def choix(self) -> tuple[str, int] | None:
        """The chosen dotation and year, if one the projet can be given."""
        dotation, _, annee = self.request.GET.get("choix", "").partition("-")
        for possible, annee_possible, existe in self.object.dotations_ajoutables:
            if (possible, str(annee_possible)) == (dotation, annee) and not existe:
                return possible, annee_possible
        return None

    def get_form(self, data=None):
        dotation, annee = self.choix
        return self.form_class(
            data=data,
            projet=self.object,
            dotation=dotation,
            annee=annee,
            user=self.request.user,
        )

    def get_context(self):
        return {**super().get_context(), "choix": self.request.GET.get("choix", "")}

    def render(self, *, oob=False, **extra):
        if self.choix is None:
            return render_to_string(
                "includes/forms/_new_dotation_card_empty.html",
                {**self.get_context(), "oob": oob},
                request=self.request,
            )
        return super().render(oob=oob, **extra)

    def on_get(self):
        if self.choix is not None:
            self.form = self.get_form()
            self.form.fields["annee"].widget.focus_checked = True
        return HttpResponse(self.render())

    def on_post(self):
        if self.choix is None:
            raise Http404
        return super().on_post()

    def on_valid(self):
        try:
            self.form.save()
        except DsServiceException as e:
            self.form.add_error(None, str(e))
            return self.on_invalid()
        messages.success(
            self.request,
            f"La dotation {self.form.instance.dotation} a été ajoutée sur la "
            f"campagne {self.form.instance.enveloppe.annee}.",
        )
        return HttpResponseClientRefresh()

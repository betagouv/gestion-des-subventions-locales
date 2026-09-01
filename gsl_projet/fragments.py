from gsl_core.fragments import Fragment
from gsl_projet.forms import (
    DotationProjetAssietteForm,
    DotationProjetForm,
    ProjetBudgetVertForm,
    ProjetZonageForm,
)
from gsl_projet.models import DotationProjet, Projet


class ProjetFragment(Fragment):
    context_object_name = "projet"


class ProjetActionsFragment(ProjetFragment):
    name = "projet_actions"
    template_name = "includes/projet_detail/_projet_actions.html"

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


class DotationProjetFormFragment(FormFragment):
    context_object_name = "dotation_projet"
    route_params = "<int:pk>"

    @classmethod
    def get_queryset(cls, request):
        return DotationProjet.objects.filter(
            projet__in=Projet.objects.active().for_user(request.user)
        )


class DetrAvisCommissionFragment(DotationProjetFormFragment):
    name = "detr_avis_commission_form"
    form_class = DotationProjetForm
    template_name = "includes/forms/_detr_avis_commission_form.html"


class AssietteDotationFragment(DotationProjetFormFragment):
    name = "assiette_dotation_form"
    form_class = DotationProjetAssietteForm
    template_name = "includes/forms/_assiette_dotation_projet_form.html"

    @classmethod
    def get_queryset(cls, request):
        return super().get_queryset(request).filter(projet__notified_at__isnull=True)

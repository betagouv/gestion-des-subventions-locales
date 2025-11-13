from logging import getLogger

from django import forms
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.forms import ModelForm
from django.utils import timezone
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.mixins import DsUpdatableFields
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService
from gsl_notification.validators import document_file_validator
from gsl_programmation.models import Enveloppe
from gsl_projet.forms import DSUpdateMixin
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.utils import compute_taux
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.services.simulation_projet_service import SimulationProjetService

logger = getLogger(__name__)


def _add_enveloppe_projets_to_simulation(simulation: Simulation):
    simulation_perimetre = simulation.enveloppe.perimetre
    simulation_dotation = simulation.enveloppe.dotation
    selected_projets = Projet.objects.for_perimetre(simulation_perimetre)
    selected_projets = selected_projets.for_current_year()
    selected_dotation_projet = DotationProjet.objects.filter(
        projet__in=selected_projets, dotation=simulation_dotation
    ).select_related(
        "projet",
        "projet__dossier_ds",
    )

    for dotation_projet in selected_dotation_projet:
        SimulationProjetService.create_or_update_simulation_projet_from_dotation_projet(
            dotation_projet, simulation
        )


class SimulationForm(DsfrBaseForm, ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["enveloppe"].queryset = Enveloppe.objects.filter(
            Q(perimetre=user.perimetre)
            | Q(deleguee_by__perimetre=user.perimetre)
            | Q(deleguee_by__deleguee_by__perimetre=user.perimetre)
        )

    def save(self, commit=True):
        self.instance.created_by = self.user
        instance: Simulation = super().save(commit=commit)
        _add_enveloppe_projets_to_simulation(instance)
        return instance

    class Meta:
        model = Simulation
        fields = ["title", "enveloppe"]


class SimulationProjetForm(DSUpdateMixin, ModelForm, DsfrBaseForm):
    assiette = forms.DecimalField(
        label="Montant des dépenses éligibles retenues (€)",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        localize=True,
        widget=forms.TextInput(attrs={"form": "simulation_projet_form", "min": 0}),
    )

    montant = forms.DecimalField(
        label="Montant prévisionnel accordé (€)",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        localize=True,
        widget=forms.TextInput(attrs={"form": "simulation_projet_form", "min": 0}),
    )

    taux = forms.DecimalField(
        label="Taux de subvention (%)",
        max_digits=6,
        decimal_places=3,
        min_value=0,
        max_value=100,
        required=False,
        localize=True,
        widget=forms.TextInput(
            attrs={"form": "simulation_projet_form", "min": 0, "max": 100}
        ),
    )

    class Meta:
        model = SimulationProjet
        fields = ["montant"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["taux"].initial = self.instance.taux

        dotation_projet = (
            self.instance.dotation_projet
            if self.instance and self.instance.dotation_projet
            else None
        )
        if dotation_projet:
            self.fields["assiette"].initial = dotation_projet.assiette

    def clean(self):
        """
        Si le montant et/ou l'assiette a changé, on recalcule le taux.
        Sinon, on regarde si le taux a changé. Si oui, on recalcule le montant.
        """
        cleaned_data = super().clean()
        simulation_projet = self.instance
        dotation_projet: DotationProjet = self.instance.dotation_projet

        if "assiette" in self.changed_data or "montant" in self.changed_data:
            assiette = cleaned_data.get("assiette")
            if assiette is None:
                assiette = dotation_projet.dossier_ds.finance_cout_total

            computed_taux = compute_taux(cleaned_data.get("montant"), assiette)

            if computed_taux != self.fields["taux"].initial:
                self.changed_data.append("taux")

            cleaned_data["taux"] = computed_taux

        else:
            if "taux" in self.changed_data:
                computed_montant = DotationProjetService.compute_montant_from_taux(
                    simulation_projet.dotation_projet, cleaned_data.get("taux")
                )
                cleaned_data["montant"] = computed_montant

        dotation_projet.assiette = cleaned_data.get("assiette")
        dotation_projet.clean()

        return cleaned_data

    def save(self, commit=True):
        instance: SimulationProjet = super().save(commit=False)
        return self._save_with_ds(instance, commit)

    def get_dossier_ds(self, instance):
        return instance.projet.dossier_ds

    def get_fields(self) -> list[DsUpdatableFields]:
        if self.instance.status == SimulationProjet.STATUS_ACCEPTED:
            return ["assiette", "montant", "taux"]
        return ["assiette"]

    def reset_field(self, field, instance):
        self._reset_field(field, instance, instance.dotation_projet)

    def post_save(self, instance):
        instance.dotation_projet.save()

    def _reset_field(
        self, field: str, instance: SimulationProjet, dotation_projet: DotationProjet
    ):
        if field == "assiette":
            self.cleaned_data["assiette"] = self["assiette"].initial
            dotation_projet.assiette = self["assiette"].initial
            self.cleaned_data["taux"] = compute_taux(
                instance.montant, dotation_projet.assiette
            )

        if field == "montant":
            self.cleaned_data["montant"] = self["montant"].initial
            instance.montant = self["montant"].initial
            self.cleaned_data["taux"] = compute_taux(
                instance.montant, dotation_projet.assiette
            )

        if field == "taux":
            initial_taux = self.fields["taux"].initial
            self.cleaned_data["taux"] = initial_taux
            instance.montant = DotationProjetService.compute_montant_from_taux(
                dotation_projet, initial_taux
            )
            self.cleaned_data["montant"] = instance.montant


class RefuseProjetForm(DsfrBaseForm, forms.Form):
    justification = forms.CharField(
        label="Motivation envoyée au demandeur (obligatoire)",
        help_text="Expliquez pourquoi ce dossier est refusé",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    justification_file = forms.FileField(
        label="Ajouter un justificatif (optionnel)",
        validators=[document_file_validator],
        help_text=f"Taille maximale {settings.MAX_POST_FILE_SIZE_IN_MO} Mo. Formats supportés : jpg, png, pdf.",
        required=False,
    )

    def __init__(self, instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulation_projet = instance

    def save(self, user: Collegue):
        with transaction.atomic():
            self.simulation_projet.dotation_projet.refuse(
                enveloppe=self.simulation_projet.enveloppe
            )
            self.simulation_projet.dotation_projet.save()
            # Dossier was recently refreshed DS thanks to RefuseProjetModalView.
            # Race conditions remain possible, but should be rare enough and just fail without any side effect.
            if self.simulation_projet.dossier.ds_state == Dossier.STATE_EN_CONSTRUCTION:
                DsMutator().dossier_passer_en_instruction(
                    dossier_id=self.simulation_projet.dossier.ds_id,
                    instructeur_id=user.ds_id,
                )

            DsMutator().dossier_refuser(
                self.simulation_projet.dossier,
                user.ds_id,
                motivation=self.cleaned_data["justification"],
                document=self.cleaned_data["justification_file"],
            )
            self.simulation_projet.dotation_projet.programmation_projet.notified_at = (
                timezone.now()
            )
            self.simulation_projet.dotation_projet.programmation_projet.save()


class DismissProjetForm(DsfrBaseForm, forms.Form):
    justification = forms.CharField(
        label="Motivation envoyée au demandeur (obligatoire)",
        help_text="Expliquez pourquoi ce dossier est classé sans suite",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulation_projet = instance

    def save(self, user: Collegue):
        with transaction.atomic():
            self.simulation_projet.dotation_projet.dismiss(
                enveloppe=self.simulation_projet.enveloppe
            )
            self.simulation_projet.dotation_projet.save()
            # Dossier was recently refreshed DS thanks to DismissProjetModalView.
            # Race conditions remain possible, but should be rare enough and just fail without any side effect.
            if self.simulation_projet.dossier.ds_state == Dossier.STATE_EN_CONSTRUCTION:
                DsMutator().dossier_passer_en_instruction(
                    dossier_id=self.simulation_projet.dossier.ds_id,
                    instructeur_id=user.ds_id,
                )

            ds_service = DsService()
            ds_service.dismiss_in_ds(
                self.simulation_projet.dossier,
                user,
                motivation=self.cleaned_data["justification"],
            )
            self.simulation_projet.dotation_projet.programmation_projet.notified_at = (
                timezone.now()
            )
            self.simulation_projet.dotation_projet.programmation_projet.save()

from logging import getLogger

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms import ModelForm
from django.utils import timezone
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService
from gsl_notification.validators import document_file_validator
from gsl_programmation.models import Enveloppe
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
)
from gsl_projet.models import (
    DotationProjet,
    Projet,
)
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
        ).order_by(
            "dotation",
            "-perimetre__region",
            "-perimetre__departement",
            "-perimetre__arrondissement",
        )

    def save(self, commit=True):
        self.instance.created_by = self.user
        instance: Simulation = super().save(commit=commit)
        _add_enveloppe_projets_to_simulation(instance)
        return instance

    class Meta:
        model = Simulation
        fields = ["title", "enveloppe"]


class SimulationProjetForm(ModelForm, DsfrBaseForm):
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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
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

    def save(self, commit=True) -> tuple[SimulationProjet, str | None]:
        instance: SimulationProjet = super().save(commit=False)
        error_msg = None
        if not commit:
            return instance, error_msg

        if instance.dotation_projet.status == PROJET_STATUS_ACCEPTED:
            try:
                instance.dotation_projet.accept(
                    montant=instance.montant,
                    enveloppe=instance.enveloppe,
                    user=self.user,
                )
            except DsServiceException as e:
                error_msg = f"Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. {str(e)}"

        if error_msg is None:
            instance.save()
            instance.dotation_projet.save()

        return instance, error_msg


class SimulationProjetStatusForm(DsfrBaseForm, forms.ModelForm):
    """
    A form to centralize simulation status update **which does not trigger
    notification** (e.g., all updates except refusal or dismissal of projects which have no other
    processing dotation).
    """

    def clean(self):
        cleaned_data = super().clean()

        if self.instance.projet.notified_at:
            raise ValidationError(
                "Le statut d'un projet déjà notifié ne peut être modifié."
            )

        return cleaned_data

    @transaction.atomic
    def save(self, status, user: Collegue, commit=True):
        if status == SimulationProjet.STATUS_ACCEPTED:
            self.instance.dotation_projet.accept(
                montant=self.instance.montant,
                enveloppe=self.instance.enveloppe,
                user=user,
            )
        elif status == SimulationProjet.STATUS_REFUSED:
            self.instance.dotation_projet.refuse(enveloppe=self.instance.enveloppe)
        elif status == SimulationProjet.STATUS_DISMISSED:
            self.instance.dotation_projet.dismiss(enveloppe=self.instance.enveloppe)
        elif (
            status in SimulationProjet.SIMULATION_PENDING_STATUSES
            and self.instance.status not in SimulationProjet.SIMULATION_PENDING_STATUSES
        ):
            self.instance.dotation_projet.set_back_status_to_processing(user)

        self.instance.dotation_projet.save()
        self.instance.status = status
        self.instance.save()

        return self.instance

    class Meta:
        model = SimulationProjet
        fields = ()


class RefuseProjetForm(SimulationProjetStatusForm):
    justification = forms.CharField(
        label="Motivation envoyée au demandeur (obligatoire)",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    justification_file = forms.FileField(
        label="Ajouter un justificatif (optionnel)",
        validators=[document_file_validator],
        help_text=f"Taille maximale {settings.MAX_POST_FILE_SIZE_IN_MO} Mo. Formats supportés : jpg, png, pdf.",
        required=False,
    )

    @transaction.atomic
    def save(self, status, user: Collegue):
        super().save(status, user)

        # Dossier was recently refreshed DN thanks to RefuseProjetModalView.
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
        if self.instance.dossier.ds_state == Dossier.STATE_EN_CONSTRUCTION:
            DsMutator().dossier_passer_en_instruction(
                dossier_id=self.instance.dossier.ds_id,
                instructeur_id=user.ds_id,
            )

        DsMutator().dossier_refuser(
            self.instance.dossier,
            user.ds_id,
            motivation=self.cleaned_data["justification"],
            document=self.cleaned_data["justification_file"],
        )
        self.instance.projet.notified_at = timezone.now()
        self.instance.projet.save()

    class Meta(SimulationProjetStatusForm.Meta):
        model = SimulationProjet
        fields = (
            "justification",
            "justification_file",
        )


class DismissProjetForm(SimulationProjetStatusForm):
    justification = forms.CharField(
        label="Motivation envoyée au demandeur (obligatoire)",
        required=True,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    @transaction.atomic
    def save(self, status, user: Collegue):
        super().save(status, user)
        # Dossier was recently refreshed DN thanks to DismissProjetModalView.
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
        if self.instance.dossier.ds_state == Dossier.STATE_EN_CONSTRUCTION:
            DsMutator().dossier_passer_en_instruction(
                dossier_id=self.instance.dossier.ds_id,
                instructeur_id=user.ds_id,
            )

        ds_service = DsService()
        ds_service.dismiss_in_ds(
            self.instance.dossier,
            user,
            motivation=self.cleaned_data["justification"],
        )
        self.instance.projet.notified_at = timezone.now()
        self.instance.projet.save()

    class Meta(SimulationProjetStatusForm.Meta):
        model = SimulationProjet
        fields = ("justification",)

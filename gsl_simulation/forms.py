from logging import getLogger

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.mixins import DsUpdatableFields
from gsl_notification.validators import document_file_validator
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.forms import DSUpdateMixin
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.utils import compute_taux
from gsl_simulation.models import SimulationProjet

logger = getLogger(__name__)


class SimulationForm(DsfrBaseForm):
    title = forms.CharField(
        label="Titre de la simulation", max_length=100, required=True
    )
    dotation = forms.ChoiceField(
        label="Dotation associée",
        choices=[
            ("", "Choisir un fonds de dotation"),
            (DOTATION_DETR, DOTATION_DETR),
            (DOTATION_DSIL, DOTATION_DSIL),
        ],
        required=True,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned_data = super().clean()
        dotation = cleaned_data.get("dotation")
        if self.user.perimetre is None:
            raise ValidationError(
                "Votre compte n’est pas associé à un périmètre. Contactez l’équipe."
            )

        if dotation == DOTATION_DETR:
            if self.user.perimetre.type == Perimetre.TYPE_REGION:
                raise ValidationError(
                    f"Votre compte est associé à un périmètre régional ({self.user.perimetre}), vous ne pouvez pas créer une simulation de programmation pour un fonds de dotation DETR."
                )

        return cleaned_data


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
        widget=forms.Textarea,
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

    def save(self, instructeur_id):
        with transaction.atomic():
            self.simulation_projet.dotation_projet.refuse(
                enveloppe=self.simulation_projet.enveloppe
            )
            self.simulation_projet.dotation_projet.save()
            DsMutator().dossier_refuser(
                self.simulation_projet.dossier,
                instructeur_id,
                motivation=self.cleaned_data["justification"],
            )

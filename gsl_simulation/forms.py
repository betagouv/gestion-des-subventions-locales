from logging import getLogger

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Collegue, Perimetre
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.utils import compute_taux
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.projet_updater import process_projet_update
from gsl_simulation.utils import build_error_message

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

    def __init__(self, *args, **kwargs):
        self.user: Collegue | None = None
        if "user" in kwargs:
            self.user = kwargs.pop("user")
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
            computed_taux = compute_taux(
                cleaned_data.get("montant"), cleaned_data.get("assiette")
            )
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
        instance = super().save(commit=False)
        dotation_projet = instance.dotation_projet

        error_msg = None
        if commit:
            if self.user is None:
                logger.warning(
                    "No user provided to SimulationProjetForm.save, can't save to DS"
                )
            else:
                errors, blocking = process_projet_update(
                    self, instance.projet.dossier_ds, self.user, ["assiette"]
                )
                if blocking:
                    error_msg = f"Une erreur est survenue lors de la mise à jour des informations sur Démarches Simplifiées. {errors['all']}"
                    return (
                        self.instance,
                        error_msg,
                    )

                for field, _ in errors.items():
                    self._reset_field(field, instance, dotation_projet)

                if errors:
                    fields_msg = build_error_message(errors)
                    error_msg = f"Une erreur est survenue lors de la mise à jour de certaines informations sur Démarches Simplifiées ({fields_msg}). Ces modifications n'ont pas été enregistrées."

            dotation_projet.save()
            instance.save()

        return instance, error_msg

    # Private

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
            initial_taux = self.initial["taux"]
            self.cleaned_data["taux"] = initial_taux
            instance.montant = DotationProjetService.compute_montant_from_taux(
                dotation_projet, initial_taux
            )
            self.cleaned_data["montant"] = instance.montant

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Perimetre
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.utils import compute_taux
from gsl_simulation.models import SimulationProjet


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
        dotation_projet = self.instance.dotation_projet

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

    # TODO test it
    def save(self, commit=True, field_exceptions=None):
        instance = super().save(commit=False)
        save_assiette = True

        if field_exceptions is not None:
            for field in field_exceptions:
                if field == "assiette":
                    save_assiette = False
                else:
                    setattr(instance, field, self.initial[field])

        dotation_projet = instance.dotation_projet
        if dotation_projet and not (save_assiette):
            dotation_projet.assiette = self.fields["assiette"].initial

        if commit:
            dotation_projet.save()
            instance.save()

        return instance

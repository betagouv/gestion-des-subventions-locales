from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Perimetre
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.services.dotation_projet_services import DotationProjetService
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
        widget=forms.NumberInput(attrs={"form": "simulation_projet_form", "min": 0}),
    )

    montant = forms.DecimalField(
        label="Montant prévisionnel accordé (€)",
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"form": "simulation_projet_form", "min": 0}),
    )

    taux = forms.DecimalField(
        label="Taux de subvention (%)",
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
        widget=forms.NumberInput(
            attrs={"form": "simulation_projet_form", "min": 0, "max": 100}
        ),
    )

    class Meta:
        model = SimulationProjet
        fields = ["montant", "taux"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dotation_projet = (
            self.instance.dotation_projet
            if self.instance and self.instance.dotation_projet
            else None
        )
        if dotation_projet:
            self.fields["assiette"].initial = dotation_projet.assiette

    def clean(self):
        cleaned_data = super().clean()
        simulation_projet = self.instance
        dotation_projet = self.instance.dotation_projet
        dotation_projet.clean()

        new_montant = cleaned_data.get("montant")
        new_taux = cleaned_data.get("taux")
        has_montant_changed = simulation_projet.montant != new_montant
        has_taux_changed = simulation_projet.taux != new_taux

        if has_montant_changed:
            computed_taux = DotationProjetService.compute_taux_from_montant(
                simulation_projet.dotation_projet, new_montant
            )

            if has_taux_changed:
                if computed_taux != new_taux:
                    self.add_error(
                        "montant", "Le montant doit être cohérent avec le taux."
                    )
                    self.add_error(
                        "taux", "Le taux doit être cohérent avec le montant."
                    )
                    raise ValidationError(
                        "Le montant et le taux ne sont pas cohérents. Veuillez vérifier vos données."
                    )

            else:
                cleaned_data["taux"] = computed_taux

        elif has_taux_changed:
            computed_montant = DotationProjetService.compute_montant_from_taux(
                simulation_projet.dotation_projet, new_taux
            )
            cleaned_data["montant"] = computed_montant

        return cleaned_data

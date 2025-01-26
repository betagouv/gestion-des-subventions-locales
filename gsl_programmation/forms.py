from django import forms
from django.core.exceptions import ValidationError
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Perimetre


class SimulationForm(DsfrBaseForm):
    title = forms.CharField(
        label="Titre de la simulation", max_length=100, required=True
    )
    dotation = forms.ChoiceField(
        label="Dotation associée",
        choices=[
            ("", "Choisir un fonds de dotation"),
            ("DETR", "DETR"),
            ("DSIL", "DSIL"),
        ],
        required=True,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned_data = super().clean()

        if self.user.perimetre is None:
            raise ValidationError("Vous n’avez pas de périmètre. Contactez l’équipe.")

        dotation = cleaned_data.get("dotation")
        if dotation == "DETR":
            if self.user.perimetre.type == Perimetre.TYPE_REGION:
                raise ValidationError(
                    f"Vous n'avez pas de département associé à votre périmètre ({self.user.perimetre}). Contactez l'équipe."
                )

        return cleaned_data

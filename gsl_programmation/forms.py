from django import forms
from dsfr.forms import DsfrBaseForm


class SimulationForm(DsfrBaseForm):
    title = forms.CharField(label="Titre de la simulation", max_length=100)
    dotation = forms.ChoiceField(
        label="Dotation associée",
        choices=[
            ("", "Choisir un fond de dotation"),
            ("DETR", "DETR"),
            ("DSIL", "DSIL"),
        ],
    )

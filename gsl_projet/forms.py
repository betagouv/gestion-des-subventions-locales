from django import forms
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_projet.models import Projet


class ProjetForm(ModelForm, DsfrBaseForm):
    AVIS_DETR_CHOICES = [
        (None, "En cours"),  # Remplace "Inconnu" par "En cours"
        (True, "Oui"),
        (False, "Non"),
    ]

    avis_commission_detr = forms.ChoiceField(
        label="Sélectionner l'avis de la commission d'élus DETR :",
        choices=AVIS_DETR_CHOICES,
        required=False,
    )

    BUDGET_VERT_CHOICES = [
        (None, "Non Renseigné"),
        (True, "Oui"),
        (False, "Non"),
    ]

    is_budget_vert = forms.ChoiceField(
        label="Transition écologique", choices=BUDGET_VERT_CHOICES, required=False
    )

    class Meta:
        model = Projet
        fields = [
            "is_in_qpv",
            "is_attached_to_a_crte",
            "avis_commission_detr",
            "is_budget_vert",
        ]

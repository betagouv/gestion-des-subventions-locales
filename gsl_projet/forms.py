from django import forms
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_projet.models import DotationProjet


class DotationProjetForm(ModelForm, DsfrBaseForm):
    AVIS_DETR_CHOICES = [
        (None, "En cours"),
        (True, "Oui"),
        (False, "Non"),
    ]

    detr_avis_commission = forms.ChoiceField(
        label="Sélectionner l'avis de la commission d'élus DETR :",
        choices=AVIS_DETR_CHOICES,
        required=False,
        widget=forms.Select(attrs={"form": "simulation_projet_form"}),
    )

    BUDGET_VERT_CHOICES = [
        (None, "Non Renseigné"),
        (True, "Oui"),
        (False, "Non"),
    ]

    is_budget_vert = forms.ChoiceField(
        label="Transition écologique",
        choices=BUDGET_VERT_CHOICES,
        required=False,
        widget=forms.Select(attrs={"form": "simulation_projet_form"}),
    )

    is_in_qpv = forms.BooleanField(
        label="Projet situé en QPV",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "simulation_projet_form"}),
    )

    is_attached_to_a_crte = forms.BooleanField(
        label="Projet rattaché à un CRTE",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "simulation_projet_form"}),
    )

    class Meta:
        model = DotationProjet
        fields = [
            "detr_avis_commission",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        projet = (
            self.instance.projet if self.instance and self.instance.projet else None
        )
        if projet:
            self.fields["is_budget_vert"].initial = projet.is_budget_vert
            self.fields["is_in_qpv"].initial = projet.is_in_qpv
            self.fields["is_attached_to_a_crte"].initial = projet.is_attached_to_a_crte

    def save(self, commit=True):
        instance = super().save(commit=False)

        projet = instance.projet
        if projet:
            projet.is_budget_vert = self.cleaned_data.get("is_budget_vert")
            projet.is_in_qpv = self.cleaned_data.get("is_in_qpv")
            projet.is_attached_to_a_crte = self.cleaned_data.get(
                "is_attached_to_a_crte"
            )
            projet.save()

        if commit:
            instance.save()
        return instance

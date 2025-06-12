from django import forms
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_projet.constants import DOTATION_CHOICES
from gsl_projet.models import CategorieDetr, DotationProjet, Projet, ProjetNote
from gsl_projet.services.projet_services import ProjetService


class ProjetForm(ModelForm, DsfrBaseForm):
    BUDGET_VERT_CHOICES = [
        (None, "Non Renseigné"),
        (True, "Oui"),
        (False, "Non"),
    ]

    is_budget_vert = forms.ChoiceField(
        label="Transition écologique",
        choices=BUDGET_VERT_CHOICES,
        required=False,
        widget=forms.Select(attrs={"form": "projet_form"}),
    )

    is_in_qpv = forms.BooleanField(
        label="Projet situé en QPV",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    is_attached_to_a_crte = forms.BooleanField(
        label="Projet rattaché à un CRTE",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    dotations = forms.MultipleChoiceField(
        choices=DOTATION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"form": "projet_form"}),
    )

    class Meta:
        model = Projet
        fields = [
            "is_budget_vert",
            "is_in_qpv",
            "is_attached_to_a_crte",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dotations"].initial = self.instance.dotations

    def is_valid(self):
        valid = super().is_valid()
        if not self.cleaned_data.get("dotations"):
            self.add_error("dotations", "Veuillez sélectionner au moins une dotation.")
            valid = False
        return valid

    def save(self, commit=True):
        instance = super().save(commit=commit)
        dotations = self.cleaned_data.get("dotations")
        if dotations:
            ProjetService.update_dotation(instance, dotations)

        return instance


class DotationProjetForm(ModelForm):
    DETR_AVIS_CHOICES = [
        (None, "En cours"),
        (True, "Oui"),
        (False, "Non"),
    ]

    detr_avis_commission = forms.ChoiceField(
        label="Sélectionner l'avis de la commission d'élus DETR :",
        choices=DETR_AVIS_CHOICES,
        required=False,
        widget=forms.Select(
            attrs={"form": "dotation_projet_form", "class": "fr-select"}
        ),
    )

    detr_categories = forms.ModelMultipleChoiceField(
        queryset=CategorieDetr.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"form": "dotation_projet_form"}),
        label="Catégories d'opération DETR",
    )

    def __init__(self, *args, departement=None, **kwargs):
        super().__init__(*args, **kwargs)
        departement = (
            self.instance.projet.perimetre.departement if self.instance.projet else None
        )
        if departement is not None:
            self.fields[
                "detr_categories"
            ].queryset = CategorieDetr.objects.most_recent_for_departement(departement)
        else:
            self.fields["detr_categories"].queryset = CategorieDetr.objects.none()
        self.fields["detr_categories"].label_from_instance = lambda obj: obj.label

    def clean_detr_avis_commission(self):
        value = self.cleaned_data.get("detr_avis_commission")
        if value == "":
            return None
        if value == "True":
            return True
        if value == "False":
            return False
        return value

    class Meta:
        model = DotationProjet
        fields = [
            "detr_avis_commission",
            "detr_categories",
        ]


class ProjetNoteForm(ModelForm, DsfrBaseForm):
    title = forms.CharField(
        label="Titre de la note",
    )
    content = forms.CharField(
        label="Note",
        widget=forms.Textarea(attrs={"rows": 6}),
    )

    class Meta:
        model = ProjetNote
        fields = [
            "title",
            "content",
        ]

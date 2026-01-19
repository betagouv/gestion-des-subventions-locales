from logging import getLogger

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import ModelForm
from dsfr.forms import DsfrBaseForm

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.services import DsService
from gsl_projet.constants import (
    DOTATION_CHOICES,
    POSSIBLE_DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.models import CategorieDetr, DotationProjet, Projet, ProjetNote

logger = getLogger(__name__)


class ProjetForm(ModelForm, DsfrBaseForm):
    is_budget_vert = forms.BooleanField(
        label="Projet concourant à la transition écologique au sens budget vert",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
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

    is_frr = forms.BooleanField(
        label="Projet situé en FRR",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    is_acv = forms.BooleanField(
        label="Projet rattaché à un programme Action coeurs de Ville (ACV)",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    is_pvd = forms.BooleanField(
        label="Projet rattaché à un programme Petites villes de demain (PVD)",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    is_va = forms.BooleanField(
        label="Projet rattaché à un programme Villages d'avenir",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    is_autre_zonage_local = forms.BooleanField(
        label="Projet rattaché à un autre zonage local",
        required=False,
        widget=forms.CheckboxInput(attrs={"form": "projet_form"}),
    )

    is_contrat_local = forms.BooleanField(
        label="Projet rattaché à un contrat local",
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
            "is_frr",
            "is_acv",
            "is_pvd",
            "is_va",
            "is_autre_zonage_local",
            "is_contrat_local",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dotations"].initial = self.instance.dotations
        self.user = user

    def is_valid(self):
        valid = super().is_valid()
        if not self.cleaned_data.get("dotations"):
            self.add_error("dotations", "Veuillez sélectionner au moins une dotation.")
            valid = False
        return valid

    def clean_dotations(self):
        dotations = self.cleaned_data.get("dotations")
        if self.instance.notified_at and set(dotations) != set(self.instance.dotations):
            raise ValidationError(
                "Les dotations d'un projet déjà notifié ne peuvent être modifiées."
            )
        return dotations

    @transaction.atomic
    def save(self, commit=True):
        instance: Projet = super().save(commit=False)
        if not commit:
            return instance

        ds_service = DsService()
        ds_service.update_checkboxes_annotations(
            dossier=instance.dossier_ds,
            user=self.user,
            annotations_to_update={
                "annotations_is_qpv": self.cleaned_data.get("is_in_qpv"),
                "annotations_is_crte": self.cleaned_data.get("is_attached_to_a_crte"),
                "annotations_is_budget_vert": self.cleaned_data.get("is_budget_vert"),
                "annotations_is_frr": self.cleaned_data.get("is_frr"),
                "annotations_is_acv": self.cleaned_data.get("is_acv"),
                "annotations_is_pvd": self.cleaned_data.get("is_pvd"),
                "annotations_is_va": self.cleaned_data.get("is_va"),
                "annotations_is_autre_zonage_local": self.cleaned_data.get(
                    "is_autre_zonage_local"
                ),
                "annotations_is_contrat_local": self.cleaned_data.get(
                    "is_contrat_local"
                ),
            },
        )

        instance.save()

        dotations = self.cleaned_data.get("dotations")
        if dotations:
            self.update_dotation(instance, dotations, self.user)

        return instance

    @transaction.atomic
    def update_dotation(
        self, projet: Projet, dotations: list[POSSIBLE_DOTATIONS], user: Collegue
    ):
        from gsl_projet.services.dotation_projet_services import DotationProjetService

        if len(dotations) == 0:
            logger.warning(
                "Projet must have at least one dotation", extra={"projet": projet.pk}
            )
            self.add_error("dotations", "Le projet doit avoir au moins une dotation.")
            return

        if len(dotations) > 2:
            logger.warning(
                "Projet can't have more than two dotations", extra={"projet": projet.pk}
            )
            self.add_error(
                "dotations", "Le projet ne peut avoir plus de deux dotations."
            )
            return

        new_dotations = set(dotations) - set(projet.dotations)
        dotation_to_remove = set(projet.dotations) - set(dotations)

        for dotation in new_dotations:
            dotation_projet = DotationProjet.objects.create(
                projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
            )
            DotationProjetService.create_simulation_projets_from_dotation_projet(
                dotation_projet
            )

        dotation_projet_to_remove = DotationProjet.objects.filter(
            projet=projet, dotation__in=dotation_to_remove
        )

        if dotation_projet_to_remove.filter(status=PROJET_STATUS_ACCEPTED).exists():
            dotations_to_be_checked = (
                DotationProjet.objects.filter(
                    projet=projet, status=PROJET_STATUS_ACCEPTED
                )
                .exclude(dotation__in=dotation_to_remove)
                .values_list("dotation", flat=True)
            )

            ds_service = DsService()
            ds_service.update_ds_annotations_for_one_dotation(
                dossier=projet.dossier_ds,
                user=user,
                dotations_to_be_checked=list(dotations_to_be_checked),
            )

        dotation_projet_to_remove.delete()


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
            ].queryset = CategorieDetr.objects.current_for_departement(departement)
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

import os

from django import forms
from django.db.models.fields import files
from dsfr.forms import DsfrBaseForm

from config.settings import MAX_POST_FILE_SIZE_IN_MO
from gsl_notification.models import (
    Annexe,
    Arrete,
    ArreteEtLettreSignes,
    LettreNotification,
    ModeleDocument,
)
from gsl_projet.constants import ARRETE, LETTRE


class ArreteForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Arrete
        fields = ("content", "created_by", "programmation_projet", "modele")


class LettreNotificationForm(ArreteForm):
    class Meta:
        model = LettreNotification
        fields = ("content", "created_by", "programmation_projet", "modele")


class UploadedDocumentForm(forms.ModelForm, DsfrBaseForm):
    file = forms.FileField(
        required=True,
    )

    class Meta:
        abstract = True

    def clean_file(self):
        file = self.cleaned_data["file"]
        valid_mime_types = ["application/pdf", "image/png", "image/jpeg"]
        valid_extensions = [".pdf", ".png", ".jpg", ".jpeg"]

        ext = os.path.splitext(file.name)[1].lower()
        if file.content_type not in valid_mime_types or ext not in valid_extensions:
            raise forms.ValidationError(
                "Seuls les fichiers PDF, PNG ou JPEG sont acceptés."
            )

        max_size_in_mo = MAX_POST_FILE_SIZE_IN_MO
        max_size = max_size_in_mo * 1024 * 1024
        if file.size > max_size:
            raise forms.ValidationError(
                f"La taille du fichier ne doit pas dépasser {max_size_in_mo} Mo."
            )
        return file


class ArreteEtLettreSigneForm(UploadedDocumentForm):
    class Meta:
        model = ArreteEtLettreSignes
        fields = ("file", "created_by", "programmation_projet")


class AnnexeForm(UploadedDocumentForm):
    class Meta:
        model = Annexe
        fields = ("file", "created_by", "programmation_projet")


class ModeleDocumentStepZeroForm(DsfrBaseForm):
    TYPE_CHOICES = (
        (ARRETE, "Arrêté attributif"),
        (LETTRE, "Lettre de notification"),
    )
    type = forms.ChoiceField(
        label="Type de document", choices=TYPE_CHOICES, widget=forms.RadioSelect
    )


class ModeleDocumentStepOneForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = ModeleDocument
        fields = ("name", "description")


class ModeleDocumentStepTwoForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = ModeleDocument
        fields = ("logo", "logo_alt_text", "top_right_text")

    def clean_logo(self):
        file = self.cleaned_data["logo"]
        valid_mime_types = ["image/png", "image/jpeg"]
        valid_extensions = [".png", ".jpg", ".jpeg"]

        ext = os.path.splitext(file.name)[1].lower()

        if isinstance(file, files.FieldFile):  # Useful for duplicate
            if ext not in valid_extensions:
                raise forms.ValidationError(
                    "Seuls les fichiers PNG ou JPEG sont acceptés."
                )
        else:
            if file.content_type not in valid_mime_types or ext not in valid_extensions:
                raise forms.ValidationError(
                    "Seuls les fichiers PNG ou JPEG sont acceptés."
                )

        max_size_in_mo = MAX_POST_FILE_SIZE_IN_MO
        max_size = max_size_in_mo * 1024 * 1024
        if file.size > max_size:
            raise forms.ValidationError(
                f"La taille du fichier ne doit pas dépasser {max_size_in_mo} Mo."
            )
        return file


class ModeleDocumentStepThreeForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = ModeleDocument
        fields = ("content",)

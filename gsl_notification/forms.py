import os

from django import forms
from dsfr.forms import DsfrBaseForm

from gsl_notification.models import Arrete, ArreteSigne, ModeleArrete


class ArreteForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Arrete
        fields = ("content", "created_by", "programmation_projet")


class ArreteSigneForm(forms.ModelForm, DsfrBaseForm):
    file = forms.FileField(
        required=True,
    )

    class Meta:
        model = ArreteSigne
        fields = ("file", "created_by", "programmation_projet")

    def clean_file(self):
        file = self.cleaned_data["file"]
        valid_mime_types = ["application/pdf", "image/png", "image/jpeg"]
        valid_extensions = [".pdf", ".png", ".jpg", ".jpeg"]

        ext = os.path.splitext(file.name)[1].lower()
        if file.content_type not in valid_mime_types or ext not in valid_extensions:
            raise forms.ValidationError(
                "Seuls les fichiers PDF, PNG ou JPEG sont acceptés."
            )

        max_size_in_mo = 20
        max_size = max_size_in_mo * 1024 * 1024  # 20 Mo
        if file.size > max_size:
            raise forms.ValidationError(
                f"La taille du fichier ne doit pas dépasser {max_size_in_mo} Mo."
            )
        return file


class ModeleArreteStepOneForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = ModeleArrete
        fields = ("name", "description")


class ModeleArreteStepTwoForm(forms.ModelForm, DsfrBaseForm):
    class Meta:
        model = ModeleArrete
        fields = ("logo", "logo_alt_text", "top_right_text")


class ModeleArreteStepThreeForm(forms.ModelForm, DsfrBaseForm):
    content = forms.CharField(
        required=True,
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = ModeleArrete
        fields = ("content",)

import os

from django import forms
from dsfr.forms import DsfrBaseForm

from gsl_notification.models import ArreteSigne


class ArreteSigneForm(forms.ModelForm, DsfrBaseForm):
    file = forms.FileField(
        required=True,
    )

    class Meta:
        model = ArreteSigne
        fields = ["file"]

    def clean_file(self):
        file = self.cleaned_data["file"]
        valid_mime_types = ["application/pdf", "image/png", "image/jpeg"]
        valid_extensions = [".pdf", ".png", ".jpg", ".jpeg"]

        ext = os.path.splitext(file.name)[1].lower()
        if file.content_type not in valid_mime_types or ext not in valid_extensions:
            raise forms.ValidationError(
                "Seuls les fichiers PDF, PNG ou JPEG sont acceptés."
            )

        max_size = 20 * 1024 * 1024  # 20 Mo
        if file.size > max_size:
            raise forms.ValidationError(
                "La taille du fichier ne doit pas dépasser 20 Mo."
            )
        return file

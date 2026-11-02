import uuid
from zipfile import BadZipFile

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import FileExtensionValidator
from openpyxl.utils.exceptions import InvalidFileException

from gsl.celery import TASK_PRIORITY_LOW

from .importer import ChorusImportError, check_headers
from .tasks import import_chorus_file_task

IMPORT_PREFIX = "chorus/imports"


class ImportChorusFileForm(forms.Form):
    """Formulaire admin : importer un export « Journal des pièces » de Chorus."""

    file = forms.FileField(
        label="Fichier Chorus",
        help_text=(
            "Export « Journal des pièces » au format XLSX. Les lignes déjà "
            "présentes sont ignorées."
        ),
        validators=[FileExtensionValidator(["xlsx"])],
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        try:
            check_headers(file)
        except (BadZipFile, InvalidFileException):
            raise ValidationError("Le fichier n'est pas un XLSX valide.")
        except ChorusImportError as e:
            raise ValidationError(str(e))
        file.seek(0)
        return file

    def save(self):
        file = self.cleaned_data["file"]
        key = default_storage.save(
            f"{IMPORT_PREFIX}/{uuid.uuid4().hex}/{file.name}", file
        )
        import_chorus_file_task.apply_async((key,), priority=TASK_PRIORITY_LOW)

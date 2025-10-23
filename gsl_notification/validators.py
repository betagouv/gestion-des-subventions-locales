import os

from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db.models.fields.files import FieldFile


def _file_validator(
    file: FieldFile | UploadedFile, valid_mime_types, valid_extensions, type_message
):
    ext = os.path.splitext(file.name)[1].lower()

    _file = file.file if isinstance(file, FieldFile) else file
    if _file.content_type not in valid_mime_types or ext not in valid_extensions:
        raise forms.ValidationError(type_message)

    max_size_in_mo = settings.MAX_POST_FILE_SIZE_IN_MO
    max_size = max_size_in_mo * 1024 * 1024
    if file.size > max_size:
        raise forms.ValidationError(
            f"La taille du fichier ne doit pas dépasser {max_size_in_mo} Mo."
        )


def document_file_validator(file: FieldFile | UploadedFile):
    return _file_validator(
        file,
        ["application/pdf", "image/png", "image/jpeg"],
        [".pdf", ".png", ".jpg", ".jpeg"],
        "Seuls les fichiers PDF, PNG ou JPEG sont acceptés.",
    )


def logo_file_validator(file: FieldFile | UploadedFile):
    return _file_validator(
        file,
        ["image/png", "image/jpeg"],
        [".png", ".jpg", ".jpeg"],
        "Seuls les fichiers PNG ou JPEG sont acceptés.",
    )

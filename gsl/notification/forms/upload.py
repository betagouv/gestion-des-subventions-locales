import json
import os
from functools import cached_property

from django import forms
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename
from dsfr.forms import DsfrBaseForm

from gsl.notification.models import UPLOADED_DOCUMENTS, DocumentImportJob
from gsl.notification.tasks import run_document_import_job
from gsl.notification.validators import document_file_validator
from gsl.projet.constants import ProjetStatus
from gsl.projet.models import EnveloppeProjet


class PresignedUploadForm(forms.Form):
    filename = forms.CharField(error_messages={"required": "Nom de fichier manquant."})

    def clean_filename(self):
        sanitized = get_valid_filename(self.cleaned_data["filename"].strip())
        if not sanitized.lower().endswith(".pdf"):
            raise forms.ValidationError("Seuls les fichiers PDF sont acceptés.")
        return sanitized


class S3KeysField(forms.Field):
    """JSON-encoded list of S3 keys, filtered to the temp import prefix."""

    default_error_messages = {
        "invalid": "Requête invalide.",
        "required": "Aucun fichier à importer.",
    }

    def to_python(self, value):
        if value in self.empty_values:
            return []
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        if not isinstance(raw, list):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        # Never trust the client with an arbitrary bucket key.
        return [key for key in raw if DocumentImportJob.is_temp_s3_key(key)]


class ImportJobStartForm(forms.Form):
    s3_keys = S3KeysField()
    remove_qr_code = forms.BooleanField(required=False)

    def save(self, user):
        job = DocumentImportJob.objects.create(
            created_by=user,
            s3_keys=self.cleaned_data["s3_keys"],
            remove_qr_code=self.cleaned_data["remove_qr_code"],
        )
        # Tâche longue, déclenchée par un agent qui attend le résultat : priorité
        # normale (défaut). La passer en haute la ferait bloquer le worker unique
        # devant les tâches courtes non bloquantes.
        run_document_import_job.delay(str(job.pk))
        return job


class RadioSelect(forms.RadioSelect):
    """
    An empty choice value renders as a disabled option carrying
    `disabled_help_text`, so a document that cannot be picked stays visible
    with the reason why.

    The class name needs to be RadioSelect for DsfrBaseForm to do its magic
    (it dispatches on the widget class name), hence the reason being an
    instance attribute rather than a subclass.
    """

    def __init__(
        self,
        *args,
        disabled_help_text="Le document a déjà été généré pour cette dotation.",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.disabled_help_text = disabled_help_text

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        if not value:
            attrs = {**(attrs or {}), "disabled": "disabled"}
            label = {"label": label, "help_text": self.disabled_help_text}

        return super().create_option(
            name, value, label, selected if value else False, index, attrs=attrs
        )


class DragNDropFileField(forms.FileField):
    """A file field that also takes a drop."""

    template_name = "includes/_dropzone_field.html"


class UploadedDocumentAnalyzeForm(DsfrBaseForm, forms.Form):
    """
    First step of the per-projet import modal. The document type is not asked
    here — it is read from the QR codes a generated document carries, and only
    asked for (`ManualDocumentAttachForm`) when the file has none.
    """

    # TODO améliorer ce field, pour que, si une erreur apparait le set_autofocus_on_first_error fonctionne
    file = DragNDropFileField(
        label="Document à importer",
        validators=[document_file_validator],
        error_messages={"required": "Sélectionnez un document à importer."},
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg"}),
    )
    remove_qr_code = forms.BooleanField(
        required=False,
        initial=True,
        label="Retirer le QR code de suivi du document importé",
        help_text=(
            "Décochez cette case pour conserver le QR code apparent lors de "
            "la notification."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].help_text = (
            f"Taille maximale : {settings.MAX_POST_FILE_SIZE_IN_MO} Mo. "
            "Formats acceptés : jpg, png, pdf."
        )


class ManualDocumentAttachForm(DsfrBaseForm, forms.Form):
    """
    Fallback step of the import modal, when no QR code told us what the file
    is: the analyse step parked it under the temporary prefix, and the agent
    names here the dotation and the document type it belongs to.

    The projet comes from the URL and the uploader from the session, so
    neither can be aimed at another projet from the client side.
    """

    document = forms.ChoiceField(
        widget=RadioSelect(
            disabled_help_text="Ce document a déjà été importé pour cette dotation."
        ),
        required=True,
        label="Type de document",
        error_messages={
            "required": "Sélectionnez un type de document.",
            "invalid_choice": "Ce type de document ne peut pas être importé "
            "pour ce projet.",
        },
    )

    def __init__(self, *args, projet, **kwargs):
        super().__init__(*args, **kwargs)
        self.projet = projet
        self.fields["document"].choices = uploadable_document_choices(projet)

    def clean(self):
        cleaned_data = super().clean()
        key = self.data.get("key", "")
        if not DocumentImportJob.is_temp_s3_key(key):
            raise forms.ValidationError("Aucun document à importer.")
        cleaned_data["key"] = key
        return cleaned_data

    @cached_property
    def enveloppe_projet(self) -> EnveloppeProjet:
        _, dotation = self.cleaned_data["document"].split("-")
        return EnveloppeProjet.objects.get(projet=self.projet, dotation=dotation)

    @cached_property
    def document_class(self):
        document_type, _ = self.cleaned_data["document"].split("-")
        return UPLOADED_DOCUMENTS[document_type]

    def save(self, user):
        key = self.cleaned_data["key"]
        with default_storage.open(key) as parked:
            document = self.document_class.objects.create(
                enveloppe_projet=self.enveloppe_projet,
                created_by=user,
                file=File(parked, name=os.path.basename(key)),
            )
        default_storage.delete(key)
        return document


def uploadable_document_choices(projet) -> list[tuple[str, str]]:
    """`(f"{document_type}-{dotation}", label)` for every document importable
    on `projet`. A document already imported keeps its label but gets an empty
    value, which `RadioSelect` renders as a disabled option.
    """
    choices = []
    enveloppe_projets = projet.enveloppeprojet_set.filter(
        status__in=ProjetStatus.FINAL
    ).order_by("dotation")
    for enveloppe_projet in enveloppe_projets:
        dotation = enveloppe_projet.dotation
        for model in UPLOADED_DOCUMENTS.values():
            if enveloppe_projet.status not in model.required_enveloppe_projet_statuses:
                continue
            can_upload = model.can_upload(enveloppe_projet)
            choices.append(
                (
                    (f"{model.document_type}-{dotation}" if can_upload else ""),
                    f"{model.verbose_name()} {dotation.upper()}",
                )
            )
    return choices

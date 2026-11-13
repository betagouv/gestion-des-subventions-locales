import dataclasses
import os
import uuid
from dataclasses import dataclass
from secrets import token_urlsafe

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename

from dn.sync.models import Dotation
from gsl.core.models import BaseModel, Collegue, Perimetre
from gsl.notification.validators import document_file_validator, logo_file_validator
from gsl.projet.constants import ProjetStatus


def tokenized_file_in_timestamped_folder(_, filename):
    base_filename, extension = os.path.splitext(filename)
    time_path = timezone.now().strftime("%Y/%m/%d")
    return f"modeles_logos/{time_path}/{base_filename}_{token_urlsafe(8)}{extension}"


class AttributedTextChoices(models.TextChoices):
    """TextChoices whose members are declared as `value, attributes, label`:
    every field of the `attributes` dataclass becomes an attribute of the
    member, e.g. `GeneratedDocument.Type.ARRETE.short_name`."""

    def __new__(cls, value, attributes):
        member = str.__new__(cls, value)
        member._value_ = value
        for field in dataclasses.fields(attributes):
            setattr(member, field.name, getattr(attributes, field.name))
        return member


@dataclass(frozen=True)
class GeneratedDocumentAttributes:
    short_code: str
    # Position among the documents sent together: the lettre comes first.
    rank: int
    verbose_name_plural: str
    short_name: str
    is_feminine: bool
    delete_label: str
    delete_question: str
    required_enveloppe_projet_statuses: tuple[str, ...]
    status_mismatch_message: str
    modele_verbose_name: str
    modele_verbose_name_plural: str
    modele_type_label: str
    modele_delete_label: str
    article_name: str


class GeneratedDocument(models.Model):
    class Type(AttributedTextChoices):
        ARRETE = (
            "arrete",
            GeneratedDocumentAttributes(
                short_code="A",
                rank=1,
                verbose_name_plural="Arrêtés",
                short_name="Arrêté",
                is_feminine=False,
                delete_label="Suppression de l’arrêté",
                delete_question="Êtes-vous sûr de vouloir supprimer cet arrêté ?",
                required_enveloppe_projet_statuses=(ProjetStatus.ACCEPTED,),
                status_mismatch_message=(
                    "Un arrêté ne peut être associé qu'à un projet de programmation "
                    "accepté."
                ),
                modele_verbose_name="Modèle d’arrêté",
                modele_verbose_name_plural="Modèles d’arrêté",
                modele_type_label="Arrêté attributif",
                modele_delete_label="Suppression du modèle d’arrêté",
                article_name="l'arrêté",
            ),
            "Arrêté",
        )
        LETTRE = (
            "lettre",
            GeneratedDocumentAttributes(
                short_code="L",
                rank=0,
                verbose_name_plural="Lettres de notification",
                short_name="Lettre",
                is_feminine=True,
                delete_label="Suppression de la lettre de notification",
                delete_question=(
                    "Êtes-vous sûr de vouloir supprimer cette lettre de notification ?"
                ),
                required_enveloppe_projet_statuses=(ProjetStatus.ACCEPTED,),
                status_mismatch_message=(
                    "Une lettre de notification ne peut être associée qu'à un projet "
                    "de programmation accepté."
                ),
                modele_verbose_name="Modèle de lettre de notification",
                modele_verbose_name_plural="Modèles de lettre de notification",
                modele_type_label="Lettre de notification",
                modele_delete_label="Suppression du modèle de lettre de notification",
                article_name="la lettre de notification",
            ),
            "Lettre de notification",
        )
        LETTRE_REFUS = (
            "refus",
            GeneratedDocumentAttributes(
                short_code="R",
                rank=2,
                verbose_name_plural="Lettres de refus ou classement sans suite",
                short_name="Lettre de refus",
                is_feminine=True,
                delete_label=(
                    "Suppression de la lettre de refus ou classement sans suite"
                ),
                delete_question=(
                    "Êtes-vous sûr de vouloir supprimer cette lettre de refus ou "
                    "classement sans suite ?"
                ),
                required_enveloppe_projet_statuses=(
                    ProjetStatus.REFUSED,
                    ProjetStatus.DISMISSED,
                ),
                status_mismatch_message=(
                    "Une lettre de refus ou de classement sans suite ne peut être "
                    "associée qu'à un projet de programmation refusé ou classé sans "
                    "suite."
                ),
                modele_verbose_name=(
                    "Modèle de lettre de refus ou classement sans suite"
                ),
                modele_verbose_name_plural=(
                    "Modèles de lettre de refus ou classement sans suite"
                ),
                modele_type_label="Lettre de refus ou classement sans suite",
                modele_delete_label=(
                    "Suppression du modèle de lettre de refus ou classement sans suite"
                ),
                article_name="la lettre de refus ou classement sans suite",
            ),
            "Lettre de refus ou classement sans suite",
        )

    type = models.CharField("Type de document", choices=Type.choices)
    modele = models.ForeignKey("ModeleDocument", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)
    content = models.TextField(
        verbose_name="Contenu du document",
        blank=True,
        default="",
        help_text="Contenu HTML du document, utilisé pour les exports.",
    )
    size = models.IntegerField(
        verbose_name="Taille du document",
        null=True,
        blank=True,
    )
    enveloppe_projet = models.ForeignKey(
        "gsl_projet.EnveloppeProjet",
        on_delete=models.CASCADE,
        verbose_name="Enveloppe projet",
        related_name="generated_documents",
    )
    with_qr_code = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Document généré"
        verbose_name_plural = "Documents générés"
        constraints = (
            models.UniqueConstraint(
                fields=("enveloppe_projet", "type"),
                name="un_seul_document_genere_par_type",
            ),
        )

    def __str__(self):
        return f"{self.verbose_name} #{self.id}"

    def save(self, *args, **kwargs):
        from gsl.notification.utils import generate_pdf_for_generated_document

        if getattr(settings, "GENERATE_DOCUMENT_SIZE", True):
            pdf_bytes = generate_pdf_for_generated_document(
                self, with_qr_code=self.with_qr_code
            )
            self.size = len(pdf_bytes)
        super().save(*args, **kwargs)

    def clean(self):
        if hasattr(self, "modele") and self.modele.type != self.type:
            raise ValidationError("Le modèle doit être du même type que le document.")
        if hasattr(self, "enveloppe_projet"):
            if (
                hasattr(self, "modele")
                and self.enveloppe_projet.dotation != self.modele.dotation
            ):
                raise ValidationError(
                    "Le modèle doit avoir la même dotation que le projet de programmation."
                )
            if (
                self.enveloppe_projet.status
                not in self.kind.required_enveloppe_projet_statuses
            ):
                raise ValidationError(self.kind.status_mismatch_message)
        return super().clean()

    @property
    def kind(self) -> Type:
        return self.Type(self.type)

    @property
    def verbose_name(self) -> str:
        return self.kind.label

    @property
    def delete_title(self):
        return f"{self.kind.delete_label} “{self.name}“"

    @property
    def delete_question(self):
        return self.kind.delete_question

    def get_download_url(self):
        return reverse("notification:document-download", args=[self.id])

    def get_view_url(self):
        return reverse("notification:document-view", args=[self.id])

    def get_delete_url(self):
        return reverse("notification:delete-document", args=[self.id])

    @property
    def is_generated(self):
        return True

    @property
    def is_downloadable(self):
        return True

    @property
    def name(self):
        return f"{self.kind.short_name} {self.enveloppe_projet.dotation} - {self.enveloppe_projet.dossier_ds.name_for_document}.pdf"

    @property
    def article_name(self):
        return self.kind.article_name

    @property
    def file_type(self):
        return "pdf"


class ModeleDocument(models.Model):
    type = models.CharField(
        "Type de document",
        choices=[
            (document_type, document_type.modele_type_label)
            for document_type in GeneratedDocument.Type
        ],
    )

    # Metadata
    name = models.CharField(
        verbose_name="Nom du modèle", help_text="Exemple : “Modèle DSIL 2025”"
    )
    description = models.TextField(
        verbose_name="Description du modèle",
        help_text="Cette description apparaîtra en dessous du titre dans la liste des modèles, elle permet de vous aider à distinguer vos modèles",
    )
    perimetre = models.ForeignKey(
        Perimetre,
        on_delete=models.PROTECT,
        verbose_name="Périmètre",
        related_name="modeles",
    )
    dotation = models.CharField("Dotation", choices=Dotation.choices)

    # Header
    logo = models.FileField(
        verbose_name="Logo situé en haut à gauche",
        help_text="Taille maximale : 20 Mo. Formats acceptés : jpg, png.",
        upload_to=tokenized_file_in_timestamped_folder,
        validators=[logo_file_validator],
    )
    logo_alt_text = models.CharField(
        verbose_name="Texte alternatif du logo",
        help_text="Reprenez le texte contenu dans l’image du logo",
    )
    top_right_text = models.TextField(
        verbose_name="Texte situé en haut à droite",
        help_text="Affiché en haut à droite de la première page",
    )

    # Content
    content = models.TextField(
        verbose_name="Contenu",
        blank=True,
        default="",
        help_text="Contenu HTML du modèle.",
    )

    # Technical metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    # Antivirus
    last_scan = models.DateTimeField(
        verbose_name="Dernière analyse antivirus",
        null=True,
        blank=True,
    )
    is_infected = models.BooleanField(
        verbose_name="Fichier infecté",
        null=True,
    )

    class Meta:
        verbose_name = "Modèle de document"
        verbose_name_plural = "Modèles de document"

    def __str__(self):
        return self.name

    @property
    def kind(self) -> GeneratedDocument.Type:
        return GeneratedDocument.Type(self.type)

    @property
    def verbose_name(self) -> str:
        return self.kind.modele_verbose_name

    @property
    def annee(self):
        return self.created_at.year

    @property
    def delete_title(self):
        return f"{self.kind.modele_delete_label} “{self.name}“"

    @property
    def delete_question(self):
        return f"Êtes-vous sûr de vouloir supprimer ce {self.verbose_name.lower()} ?"


@dataclass(frozen=True)
class UploadedDocumentAttributes:
    delete_label: str
    delete_question: str
    required_enveloppe_projet_statuses: tuple[str, ...]
    status_mismatch_message: str = ""
    # QR document types whose scanned pages are stored as this document.
    reattach_source_document_types: tuple[str, ...] = ()
    allow_multiple: bool = False


def uploaded_document_upload_to(instance, filename):
    # Named (module-level) so it stays migration-serializable, unlike a lambda.
    folder = f"enveloppe_projet_{instance.enveloppe_projet_id}"
    return f"{instance.type}/{folder}/{filename}"


class UploadedDocument(models.Model):
    class Type(AttributedTextChoices):
        LETTRE_ET_ARRETE_SIGNES = (
            "lettre_et_arrete_signes",
            UploadedDocumentAttributes(
                delete_label="Suppression de la lettre et de l’arrêté signés",
                delete_question=(
                    "Êtes-vous sûr de vouloir supprimer cette lettre et cet arrêté "
                    "signés ?"
                ),
                required_enveloppe_projet_statuses=(ProjetStatus.ACCEPTED,),
                status_mismatch_message=(
                    "La lettre et l'arrêté signés ne peuvent être importés que pour "
                    "un projet de programmation accepté."
                ),
                reattach_source_document_types=(
                    GeneratedDocument.Type.ARRETE,
                    GeneratedDocument.Type.LETTRE,
                ),
            ),
            "Lettre et arrêté signés",
        )
        LETTRE_REFUS_SIGNEE = (
            "lettre_refus_signee",
            UploadedDocumentAttributes(
                delete_label="Suppression de la lettre de refus signée",
                delete_question=(
                    "Êtes-vous sûr de vouloir supprimer cette lettre de refus signée ?"
                ),
                required_enveloppe_projet_statuses=(
                    ProjetStatus.REFUSED,
                    ProjetStatus.DISMISSED,
                ),
                status_mismatch_message=(
                    "La lettre de refus signée ne peut être importée que pour un "
                    "projet de programmation refusé ou classé sans suite."
                ),
                reattach_source_document_types=(GeneratedDocument.Type.LETTRE_REFUS,),
            ),
            "Lettre de refus signée",
        )
        ANNEXE = (
            "annexe",
            UploadedDocumentAttributes(
                delete_label="Suppression de l’annexe",
                delete_question="Êtes-vous sûr de vouloir supprimer cette annexe ?",
                required_enveloppe_projet_statuses=ProjetStatus.FINAL,
                allow_multiple=True,
            ),
            "Annexe",
        )

    type = models.CharField("Type de document", choices=Type.choices)
    enveloppe_projet = models.ForeignKey(
        "gsl_projet.EnveloppeProjet",
        on_delete=models.CASCADE,
        verbose_name="Enveloppe projet",
        related_name="uploaded_documents",
    )
    file = models.FileField(
        upload_to=uploaded_document_upload_to, validators=[document_file_validator]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    last_scan = models.DateTimeField(
        verbose_name="Dernière analyse antivirus",
        null=True,
        blank=True,
    )
    is_infected = models.BooleanField(
        verbose_name="Fichier infecté",
        null=True,
    )

    class Meta:
        verbose_name = "Document importé"
        verbose_name_plural = "Documents importés"
        constraints = (
            models.UniqueConstraint(
                fields=("enveloppe_projet", "type"),
                condition=~Q(type="annexe"),
                name="un_seul_document_importe_par_type_hors_annexes",
            ),
        )

    def __str__(self):
        return f"{self.verbose_name} #{self.id}"

    @property
    def kind(self) -> Type:
        return self.Type(self.type)

    @property
    def verbose_name(self) -> str:
        return self.kind.label

    @property
    def delete_title(self):
        return f"{self.kind.delete_label} “{self.name}“"

    @property
    def delete_question(self):
        return self.kind.delete_question

    def clean(self):
        if (
            hasattr(self, "enveloppe_projet")
            and self.enveloppe_projet.status
            not in self.kind.required_enveloppe_projet_statuses
        ):
            raise ValidationError(self.kind.status_mismatch_message)
        return super().clean()

    @property
    def is_downloadable(self):
        if settings.BYPASS_ANTIVIRUS:
            return True
        return self.last_scan is not None and not self.is_infected

    def get_download_url(self):
        return reverse("notification:uploaded-document-download", args=[self.id])

    def get_view_url(self):
        return reverse("notification:uploaded-document-view", args=[self.id])

    def get_delete_url(self):
        return reverse("notification:delete-uploaded-document", args=[self.id])

    @property
    def name(self):
        return self.file.name.split("/")[-1]

    @property
    def file_type(self):
        return self.file.name.split(".")[-1]

    @property
    def size(self):
        return self.file.size


class DocumentImportJob(BaseModel):
    """
    Tracks an async re-import of scanned, signed documents. The browser uploads
    one or more PDFs straight to a temporary S3 prefix (presigned POST), then a
    Celery task downloads each one, virus-scans it, decodes the per-page GSL QR
    codes, and reattaches each page-group to its EnveloppeProjet as a
    lettre et arrêté signés. The row is the single source of truth for progress:
    the browser polls a view that reads this model.
    """

    # S3 prefix where the browser uploads scans before processing; the task
    # deletes these once done.
    TEMP_S3_PREFIX = "imports/"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_RUNNING, "En cours"),
        (STATUS_DONE, "Terminé"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    s3_keys = models.JSONField(default=list)
    total_pages = models.PositiveIntegerField(default=0)
    processed_pages = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict)
    remove_qr_code = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Import de documents signés"
        verbose_name_plural = "Imports de documents signés"
        ordering = ("-created_at",)

    @classmethod
    def temp_s3_key(cls, filename: str) -> str:
        return f"{cls.TEMP_S3_PREFIX}{uuid.uuid4()}/{get_valid_filename(filename)}"

    @classmethod
    def is_temp_s3_key(cls, key) -> bool:
        return isinstance(key, str) and key.startswith(cls.TEMP_S3_PREFIX)

    @property
    def file_count(self) -> int:
        return len(self.s3_keys)

    @property
    def is_running(self) -> bool:
        return self.status in (self.STATUS_PENDING, self.STATUS_RUNNING)


class ExportJob(BaseModel):
    """
    Tracks an async batch PDF export. `done()` creates this record and dispatches
    a Celery task; the browser polls a view that reads it for progress.
    """

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_FAILED = "failed"
    STATUS_DONE = "done"
    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_RUNNING, "En cours"),
        (STATUS_FAILED, "Échec"),
        (STATUS_DONE, "Terminé"),
    )

    DOCUMENT_TYPE_ARRETE_ET_LETTRE = "arrete_et_lettre"
    DOCUMENT_TYPE_CHOICES = (
        (GeneratedDocument.Type.ARRETE, "Arrêté"),
        (GeneratedDocument.Type.LETTRE, "Lettre de notification"),
        (DOCUMENT_TYPE_ARRETE_ET_LETTRE, "Arrêté et lettre"),
        (
            GeneratedDocument.Type.LETTRE_REFUS,
            "Lettre de refus ou de classement sans suite",
        ),
    )

    EXPORT_FORMAT_ONE_PDF_PER_DOC = "un_pdf_par_document"
    EXPORT_FORMAT_ONE_PDF_ALL = "un_seul_pdf_ensemble"
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT = "un_pdf_par_projet"
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED = "un_seul_pdf_groupe_par_projet"
    EXPORT_FORMAT_CHOICES = (
        (EXPORT_FORMAT_ONE_PDF_PER_DOC, "Un PDF par document"),
        (EXPORT_FORMAT_ONE_PDF_ALL, "Un seul PDF pour l'ensemble"),
        (EXPORT_FORMAT_ONE_PDF_PER_PROJECT, "Un PDF par projet"),
        (EXPORT_FORMAT_ONE_PDF_ALL_GROUPED, "Un seul PDF groupé par projet"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    # Task parameters — stored so the task only needs job_id
    enveloppe_projet_ids = models.JSONField(default=list)
    attr_names = models.JSONField(default=list)
    export_format = models.CharField(max_length=64, choices=EXPORT_FORMAT_CHOICES)
    document_type = models.CharField(max_length=32, choices=DOCUMENT_TYPE_CHOICES)
    with_qr_code = models.BooleanField(default=True)

    # Progress
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    step = models.PositiveSmallIntegerField(default=1)
    total_steps = models.PositiveSmallIntegerField(default=2)
    processed = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    # Result
    download_url = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Export de documents"
        verbose_name_plural = "Exports de documents"
        ordering = ("-created_at",)

    @property
    def step_label(self) -> str:
        if self.with_qr_code:
            return {
                1: "Première génération",
                2: "Génération avec QR code",
                3: "Création du fichier d'export",
            }.get(self.step, "")
        return {
            1: "Génération des documents",
            2: "Création du fichier d'export",
        }.get(self.step, "")

    @property
    def is_running(self) -> bool:
        return self.status in (self.STATUS_PENDING, self.STATUS_RUNNING)

import os
import uuid
from secrets import token_urlsafe

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from gsl_core.models import BaseModel, Collegue, Perimetre
from gsl_notification.validators import document_file_validator, logo_file_validator
from gsl_projet.constants import (
    ANNEXE,
    ARRETE,
    DOTATION_CHOICES,
    LETTRE,
    LETTRE_ET_ARRETE_SIGNES,
)


def tokenized_file_in_timestamped_folder(_, filename):
    base_filename, extension = os.path.splitext(filename)
    time_path = timezone.now().strftime("%Y/%m/%d")
    return f"modeles_logos/{time_path}/{base_filename}_{token_urlsafe(8)}{extension}"


class ModeleDocument(models.Model):
    TYPE_ARRETE = "arrete"
    TYPE_LETTRE = "lettre"

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
        related_name="modeles_arrete",
    )
    dotation = models.CharField("Dotation", choices=DOTATION_CHOICES)

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
        abstract = True

    def __str__(self):
        return self.name

    @property
    def annee(self):
        return self.created_at.year

    @property
    def type(self):
        raise NotImplementedError


class ModeleArrete(ModeleDocument):
    perimetre = models.ForeignKey(
        Perimetre,
        on_delete=models.PROTECT,
        verbose_name="Périmètre",
        related_name="modeles_arrete",
    )

    class Meta:
        verbose_name = "Modèle d’arrêté"
        verbose_name_plural = "Modèles d’arrêté"

    @property
    def type(self):
        return ARRETE


class ModeleLettreNotification(ModeleDocument):
    perimetre = models.ForeignKey(
        Perimetre,
        on_delete=models.PROTECT,
        verbose_name="Périmètre",
        related_name="modeles_lettre_notification",
    )

    class Meta:
        verbose_name = "Modèle de lettre de notification"
        verbose_name_plural = "Modèles de lettre de notification"

    @property
    def type(self):
        return LETTRE


class GeneratedDocument(models.Model):
    document_type = None
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

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        from gsl_notification.utils import generate_pdf_for_generated_document

        if getattr(settings, "GENERATE_DOCUMENT_SIZE", True):
            pdf_bytes = generate_pdf_for_generated_document(self)
            self.size = len(pdf_bytes)
        super().save(*args, **kwargs)

    def clean(self):
        if (
            hasattr(self, "programmation_projet")
            and hasattr(self, "modele")
            and self.programmation_projet.dotation != self.modele.dotation
        ):
            raise ValidationError(
                "Le modèle doit avoir la même dotation que le projet de programmation."
            )
        return super().clean()

    def get_download_url(self):
        return reverse(
            "notification:document-download",
            kwargs={"document_type": self.document_type, "document_id": self.id},
        )

    def get_view_url(self):
        return reverse(
            "notification:document-view",
            kwargs={"document_type": self.document_type, "document_id": self.id},
        )

    @property
    def is_generated(self):
        return True

    @property
    def is_downloadable(self):
        return True

    @property
    def name(self):
        raise NotImplementedError

    @property
    def file_type(self):
        return "pdf"


class Arrete(GeneratedDocument):
    document_type = ARRETE
    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        verbose_name="Programmation projet",
        related_name="arrete",
    )
    modele = models.ForeignKey(ModeleArrete, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Arrêté"
        verbose_name_plural = "Arrêtés"

    def __str__(self):
        return f"Arrêté #{self.id}"

    @property
    def name(self):
        return f"arrêté-attributif-{self.programmation_projet.enveloppe.dotation}-{self.created_at.strftime('%Y-%m-%d')} - {self.programmation_projet.dossier.ds_number} - {slugify(self.programmation_projet.dossier.ds_demandeur.raison_sociale)}.pdf"


class LettreNotification(GeneratedDocument):
    document_type = LETTRE
    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        verbose_name="Programmation projet",
        related_name="lettre_notification",
    )
    modele = models.ForeignKey(ModeleLettreNotification, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Lettre de notification"
        verbose_name_plural = "Lettres de notification"

    def __str__(self):
        return f"Lettre de notification #{self.id}"

    @property
    def name(self):
        return f"lettre-notification-{self.programmation_projet.enveloppe.dotation}-{self.created_at.strftime('%Y-%m-%d')} - {self.programmation_projet.dossier.ds_number} - {slugify(self.programmation_projet.dossier.ds_demandeur.raison_sociale)}.pdf"


class UploadedDocument(models.Model):
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
        abstract = True

    @property
    def is_downloadable(self):
        if settings.BYPASS_ANTIVIRUS:
            return True
        return self.last_scan is not None and not self.is_infected

    def get_download_url(self):
        return reverse(
            "notification:uploaded-document-download",
            kwargs={"document_type": self.document_type, "document_id": self.id},
        )

    def get_view_url(self):
        return reverse(
            "notification:uploaded-document-view",
            kwargs={"document_type": self.document_type, "document_id": self.id},
        )

    @property
    def name(self):
        return self.file.name.split("/")[-1]

    @property
    def file_type(self):
        return self.file.name.split(".")[-1]

    @property
    def size(self):
        return self.file.size

    @property
    def document_type(self):
        raise NotImplementedError


class LettreEtArreteSignes(UploadedDocument):
    file = models.FileField(
        upload_to="arrete_et_lettre_signes/", validators=[document_file_validator]
    )

    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="lettre_et_arrete_signes",
    )

    class Meta:
        verbose_name = "Lettre et arrêté signés"
        verbose_name_plural = "Lettres et arrêtés signés"

    def __str__(self):
        return f"Lettre et arrêté signés #{self.id}"

    @property
    def document_type(self):
        return LETTRE_ET_ARRETE_SIGNES


class DocumentImportJob(BaseModel):
    """
    Tracks an async re-import of scanned, signed documents. The browser uploads
    one or more PDFs straight to a temporary S3 prefix (presigned POST), then a
    Celery task downloads each one, virus-scans it, decodes the per-page GSL QR
    codes, and reattaches each page-group to its ProgrammationProjet as a
    LettreEtArreteSignes. The row is the single source of truth for progress:
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    # Task parameters — stored so the task only needs job_id
    pp_ids = models.JSONField(default=list)
    attr_names = models.JSONField(default=list)
    export_format = models.CharField(max_length=64)
    document_type = models.CharField(max_length=32)
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


class Annexe(UploadedDocument):
    file = models.FileField(upload_to="annexe/", validators=[document_file_validator])

    programmation_projet = models.ForeignKey(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="annexes",
    )

    class Meta:
        verbose_name = "Annexe"
        verbose_name_plural = "Annexes"

    def __str__(self):
        return f"Annexe #{self.id}"

    @property
    def document_type(self):
        return ANNEXE

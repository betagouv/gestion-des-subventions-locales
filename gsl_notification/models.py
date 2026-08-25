import os
import uuid
from secrets import token_urlsafe

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from gsl_core.models import BaseModel, Collegue, Perimetre
from gsl_notification.validators import document_file_validator, logo_file_validator
from gsl_projet.constants import (
    ARRETE,
    DOTATION_CHOICES,
    LETTRE,
    LETTRE_REFUS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)


def tokenized_file_in_timestamped_folder(_, filename):
    base_filename, extension = os.path.splitext(filename)
    time_path = timezone.now().strftime("%Y/%m/%d")
    return f"modeles_logos/{time_path}/{base_filename}_{token_urlsafe(8)}{extension}"


MODELES = {}


class VerboseNameMixin:
    @classmethod
    def verbose_name(cls, count=1):
        meta = cls._meta
        name = meta.verbose_name if count == 1 else meta.verbose_name_plural
        return name

    @property
    def delete_title(self):
        return f"{self.delete_label} “{self.name}“"


class ModeleDocument(VerboseNameMixin, models.Model):
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
        related_name="modeles_%(class)s",
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

    # Set by GeneratedDocument.__init_subclass__ for modeles that have a
    # corresponding generated document (e.g. ModeleArrete -> Arrete). Stays
    # None for modeles that don't (e.g. ModeleLettreRefus).
    generated_document_class: "type[GeneratedDocument] | None" = None

    class Meta:
        verbose_name = "Modèle de document"
        verbose_name_plural = "Modèles de document"
        abstract = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        MODELES[cls.type] = cls

    def __str__(self):
        return self.name

    @property
    def annee(self):
        return self.created_at.year

    @property
    def delete_question(self):
        return f"Êtes-vous sûr de vouloir supprimer ce {self.verbose_name().lower()} ?"


class ModeleArrete(ModeleDocument):
    type = ARRETE
    type_label = "Arrêté attributif"
    delete_label = "Suppression du modèle d’arrêté"
    article_name = "l'arrêté"

    class Meta:
        verbose_name = "Modèle d’arrêté"
        verbose_name_plural = "Modèles d’arrêté"


class ModeleLettreNotification(ModeleDocument):
    type = LETTRE
    type_label = "Lettre de notification"
    delete_label = "Suppression du modèle de lettre de notification"
    article_name = "la lettre de notification"

    class Meta:
        verbose_name = "Modèle de lettre de notification"
        verbose_name_plural = "Modèles de lettre de notification"


class ModeleLettreRefus(ModeleDocument):
    type = LETTRE_REFUS
    type_label = "Lettre de refus ou classement sans suite"
    delete_label = "Suppression du modèle de lettre de refus ou classement sans suite"
    article_name = "la lettre de refus ou classement sans suite"

    class Meta:
        verbose_name = "Modèle de lettre de refus ou classement sans suite"
        verbose_name_plural = "Modèles de lettre de refus ou classement sans suite"


GENERATED_DOCUMENTS = {}


class GeneratedDocument(VerboseNameMixin, models.Model):
    document_type: str | None = None
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
    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        verbose_name="Programmation projet",
        related_name="%(class)s",
    )
    with_qr_code = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        GENERATED_DOCUMENTS[cls.document_type] = cls
        MODELES[cls.document_type].generated_document_class = cls

    def __str__(self):
        return f"{self.verbose_name()} #{self.id}"

    def save(self, *args, **kwargs):
        from gsl_notification.utils import generate_pdf_for_generated_document

        if getattr(settings, "GENERATE_DOCUMENT_SIZE", True):
            pdf_bytes = generate_pdf_for_generated_document(
                self, with_qr_code=self.with_qr_code
            )
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
        return f"{self.short_name} {self.programmation_projet.enveloppe.dotation} - {self.programmation_projet.dossier.name_for_document}.pdf"

    @property
    def article_name(self):
        return self.modele.article_name

    @property
    def file_type(self):
        return "pdf"


class Arrete(GeneratedDocument):
    document_type = ARRETE
    delete_label = "Suppression de l’arrêté"
    delete_question = "Êtes-vous sûr de vouloir supprimer cet arrêté ?"
    short_name = "Arrêté"
    modele = models.ForeignKey(ModeleArrete, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Arrêté"
        verbose_name_plural = "Arrêtés"


class LettreNotification(GeneratedDocument):
    document_type = LETTRE
    delete_label = "Suppression de la lettre de notification"
    delete_question = (
        "Êtes-vous sûr de vouloir supprimer cette lettre de notification ?"
    )
    short_name = "Lettre"
    modele = models.ForeignKey(ModeleLettreNotification, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Lettre de notification"
        verbose_name_plural = "Lettres de notification"


class LettreRefus(GeneratedDocument):
    document_type = LETTRE_REFUS
    delete_label = "Suppression de la lettre de refus ou classement sans suite"
    delete_question = "Êtes-vous sûr de vouloir supprimer cette lettre de refus ou classement sans suite ?"
    short_name = "Lettre de refus"
    modele = models.ForeignKey(ModeleLettreRefus, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Lettre de refus ou classement sans suite"
        verbose_name_plural = "Lettres de refus ou classement sans suite"


UPLOADED_DOCUMENTS = {}


def uploaded_document_upload_to(instance, filename):
    # Named (module-level) so it stays migration-serializable, unlike a lambda.
    return f"{instance.document_type}/{filename}"


class UploadedDocument(VerboseNameMixin, models.Model):
    document_type: str | None = None
    # DotationProjet statuses for which this document can be uploaded.
    upload_statuses: tuple[str, ...] = ()
    # False => OneToOne to ProgrammationProjet: a single document, the choice is
    # disabled once one exists. True => several allowed (e.g. annexes).
    allow_multiple = False

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
        abstract = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        UPLOADED_DOCUMENTS[cls.document_type] = cls

    @classmethod
    def can_upload(cls, programmation_projet) -> bool:
        if cls.allow_multiple:
            return True
        return not cls.objects.filter(
            programmation_projet=programmation_projet
        ).exists()

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


class LettreEtArreteSignes(UploadedDocument):
    document_type = "lettre_et_arrete_signes"
    upload_statuses = (PROJET_STATUS_ACCEPTED,)
    delete_label = "Suppression de la lettre et de l’arrêté signés"
    delete_question = (
        "Êtes-vous sûr de vouloir supprimer cette lettre et cet arrêté signés ?"
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


class Annexe(UploadedDocument):
    document_type = "annexe"
    upload_statuses = (PROJET_STATUS_ACCEPTED,)
    allow_multiple = True
    delete_label = "Suppression de l’annexe"
    delete_question = "Êtes-vous sûr de vouloir supprimer cette annexe ?"

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


class LettreRefusSignee(UploadedDocument):
    document_type = "lettre_refus_signee"
    upload_statuses = (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED)
    delete_label = "Suppression de la lettre de refus signée"
    delete_question = (
        "Êtes-vous sûr de vouloir supprimer cette lettre de refus signée ?"
    )

    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="lettre_refus_signee",
    )

    class Meta:
        verbose_name = "Lettre de refus signée"
        verbose_name_plural = "Lettres de refus signées"

    def __str__(self):
        return f"Lettre de refus signée #{self.id}"


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

    DOCUMENT_TYPE_ARRETE = ARRETE
    DOCUMENT_TYPE_LETTRE = LETTRE
    DOCUMENT_TYPE_ARRETE_ET_LETTRE = "arrete_et_lettre"
    DOCUMENT_TYPE_CHOICES = (
        (ARRETE, "Arrêté"),
        (LETTRE, "Lettre de notification"),
        ("arrete_et_lettre", "Arrêté et lettre"),
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
    pp_ids = models.JSONField(default=list)
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

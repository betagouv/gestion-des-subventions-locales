import os
from secrets import token_urlsafe

from django.db import models
from django.urls import reverse
from django.utils import timezone

from gsl_core.models import Collegue, Perimetre
from gsl_projet.constants import (
    ANNEXE,
    ARRETE,
    ARRETE_ET_LETTRE_SIGNE,
    DOTATION_CHOICES,
    LETTRE,
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

    class Meta:
        verbose_name = "Modèle de document"
        verbose_name_plural = "Modèles de document"
        abstract = True

    def __str__(self):
        return f"Modèle d’arrêté {self.id} - {self.name}"

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

    def __str__(self):
        return f"Modèle d’arrêté {self.id} - {self.name}"

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

    def __str__(self):
        return f"Modèle de lettre de notification {self.id} - {self.name}"

    @property
    def type(self):
        return LETTRE


class GeneratedDocument(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)
    content = models.TextField(
        verbose_name="Contenu du document",
        blank=True,
        default="",
        help_text="Contenu HTML du document, utilisé pour les exports.",
    )

    class Meta:
        abstract = True

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
    def name(self):
        raise NotImplementedError

    @property
    def document_type(self):
        raise NotImplementedError

    @property
    def file_type(self):
        return "pdf"

    @property
    def size(self):  # TODO: Implement a proper name logic
        return 12345


class Arrete(GeneratedDocument):
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
    def document_type(self):
        return ARRETE

    @property
    def name(self):
        return f"arrêté-attributif-{self.created_at.strftime('%Y-%m-%d')}.pdf"


class LettreNotification(GeneratedDocument):
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
    def document_type(self):
        return LETTRE

    @property
    def name(self):
        return f"lettre-notification-{self.created_at.strftime('%Y-%m-%d')}.pdf"


class UploadedDocument(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    class Meta:
        abstract = True

    def get_download_url(self):  # TODO update
        return reverse(
            "notification:arrete-signe-download", kwargs={"arrete_signe_id": self.id}
        )

    def get_view_url(self):  # TODO update
        return reverse(
            "notification:arrete-signe-view", kwargs={"arrete_signe_id": self.id}
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


class ArreteSigne(UploadedDocument):
    file = models.FileField(upload_to="arrete_signe/")

    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="arrete_signe",
    )

    class Meta:
        verbose_name = "Arrêté signé"
        verbose_name_plural = "Arrêtés signés"

    def __str__(self):
        return f"Arrêté signé #{self.id}"

    @property
    def document_type(self):
        return ARRETE_ET_LETTRE_SIGNE


class Annexe(UploadedDocument):
    file = models.FileField(upload_to="annexe/")

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

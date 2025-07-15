from django.db import models
from django.urls import reverse

from gsl_core.models import Collegue, Perimetre
from gsl_projet.constants import DOTATION_CHOICES


class ModeleArrete(models.Model):
    # Metadata
    name = models.CharField(
        verbose_name="Nom du modèle", help_text="Exemple : “Modèle d’arrêté DSIL 2025”"
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
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
    )

    # Technical metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Modèle d’arrêté"
        verbose_name_plural = "Modèles d’arrêté"

    def __str__(self):
        return f"Modèle d’arrêté {self.id} - {self.name}"

    @property
    def annee(self):
        return self.created_at.year


class Arrete(models.Model):
    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        verbose_name="Programmation projet",
        related_name="arrete",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)
    content = models.TextField(
        verbose_name="Contenu de l'arrêté",
        blank=True,
        default="",
        help_text="Contenu HTML de l'arrêté, utilisé pour les exports.",
    )

    class Meta:
        verbose_name = "Arrêté"
        verbose_name_plural = "Arrêtés"

    def __str__(self):
        return f"Arrêté #{self.id}"

    def get_absolute_url(self):
        return reverse("notification:arrete-download", kwargs={"arrete_id": self.id})

    @property
    def name(self):  # TODO: Implement a proper name logic
        return f"arrêté-attributif-{self.created_at.strftime('%Y-%m-%d')}.pdf"

    @property
    def type(self):  # TODO: Implement a proper name logic
        return "pdf"

    @property
    def size(self):  # TODO: Implement a proper name logic
        return 12345


class ArreteSigne(models.Model):
    file = models.FileField(upload_to="arrete_signe/")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

    programmation_projet = models.OneToOneField(
        "gsl_programmation.ProgrammationProjet",
        on_delete=models.CASCADE,
        related_name="arrete_signe",
    )

    class Meta:
        verbose_name = "Arrêté signé"
        verbose_name_plural = "Arrêtés signés"

    def __str__(self):
        return f"Arrêté signé #{self.id} "

    def get_absolute_url(self):
        return reverse(
            "notification:arrete-signe-download", kwargs={"arrete_signe_id": self.id}
        )

    @property
    def name(self):
        return self.file.name.split("/")[-1]

    @property
    def type(self):
        return self.file.name.split(".")[-1]

    @property
    def size(self):
        return self.file.size

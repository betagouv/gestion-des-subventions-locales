from datetime import datetime
from typing import TYPE_CHECKING

from django.contrib.admin.models import LogEntry
from django.db import models
from django.utils import timezone

from gsl.projet.constants import (
    DOTATION_CHOICES,
    DS_TRAITEMENT_EVENT_ACCEPTE,
    DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
    DS_TRAITEMENT_EVENT_DEPOSE,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_REFUSE,
    DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION,
    DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION,
)

if TYPE_CHECKING:
    from gsl.projet.models import Projet


def projet_action_document_upload_to(instance, filename):
    # Named (module-level) so it stays migration-serializable, unlike a lambda.
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"notifications/{instance.projet_id}/{timestamp}/{filename}"


class ProjetActionManager(models.Manager):
    def create_from_dossier_traitements(self, projet: "Projet") -> int:
        """Parcourt tous les traitements DN du dossier et crée les
        ProjetActions manquantes (dépôt, passage en instruction, retour en
        instruction, retour en construction, notification), en associant
        `source_id` (id du Traitement DN) qui sert de clé pour ne jamais
        créer de doublon si la fonction est rejouée (ex : resynchronisation
        périodique du dossier). Retourne le nombre de ProjetActions créées."""
        event_to_action_type = {
            DS_TRAITEMENT_EVENT_DEPOSE: self.model.TYPE_DEPOT_DOSSIER,
            DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION: self.model.TYPE_PASSAGE_EN_INSTRUCTION,
            DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT: self.model.TYPE_PASSAGE_EN_INSTRUCTION,
            DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION: self.model.TYPE_RETOUR_EN_INSTRUCTION,
            DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION: self.model.TYPE_RETOUR_EN_CONSTRUCTION,
            DS_TRAITEMENT_EVENT_ACCEPTE: self.model.TYPE_NOTIFIED,
            DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT: self.model.TYPE_NOTIFIED,
            DS_TRAITEMENT_EVENT_REFUSE: self.model.TYPE_NOTIFIED,
            DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT: self.model.TYPE_NOTIFIED,
            DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE: self.model.TYPE_NOTIFIED,
        }

        traitements = projet.dossier_ds.traitements

        created_count = 0
        for traitement in traitements:
            action_type = event_to_action_type.get(traitement.get("event"))
            traitement_id = traitement.get("id")
            date_traitement = traitement.get("dateTraitement")
            if not action_type or not traitement_id or not date_traitement:
                continue

            _, created = self.get_or_create(
                projet=projet,
                source_id=traitement_id,
                defaults={
                    "action_type": action_type,
                    "source": self.model.SOURCE_DN,
                    "created_at": datetime.fromisoformat(date_traitement),
                },
            )
            created_count += created

        return created_count


class ProjetAction(models.Model):
    SOURCE_TURGOT = "turgot"
    SOURCE_DN = "dn"
    SOURCES = [(SOURCE_TURGOT, "Turgot"), (SOURCE_DN, "DN")]

    TYPE_STATUS_CHANGE = "status_change"
    TYPE_DOC_GENERATED = "doc_generated"
    TYPE_DOC_MODIFIED = "doc_modified"
    TYPE_DOC_DELETED = "doc_deleted"
    TYPE_DOC_UPLOADED = "doc_uploaded"
    TYPE_DOC_UPLOAD_DELETED = "doc_upload_deleted"
    TYPE_NOTIFIED = "notified"
    TYPE_ASSIETTE_MODIFIED = "assiette_modified"
    TYPE_DOTATION_ADDED = "dotation_added"
    TYPE_DOTATION_REMOVED = "dotation_removed"
    TYPE_MONTANT_MODIFIED = "montant_modified"
    TYPE_BOOLEAN_MODIFIED = "boolean_modified"
    TYPE_DEPOT_DOSSIER = "depot_dossier"
    TYPE_PASSAGE_EN_INSTRUCTION = "passage_en_instruction"
    TYPE_RETOUR_EN_CONSTRUCTION = "retour_en_construction"
    TYPE_RETOUR_EN_INSTRUCTION = (
        "retour_en_instruction"  # TODO, use it when this Turgot action is done
    )
    TYPE_DEACTIVATION = "deactivation"
    TYPE_REACTIVATION = "reactivation"

    ACTION_TYPES = [
        (TYPE_STATUS_CHANGE, "Changement de statut"),
        (TYPE_DOC_GENERATED, "Génération de document"),
        (TYPE_DOC_MODIFIED, "Modification de document"),
        (TYPE_DOC_DELETED, "Suppression de document généré"),
        (TYPE_DOC_UPLOADED, "Import de document"),
        (TYPE_DOC_UPLOAD_DELETED, "Suppression de document importé"),
        (TYPE_NOTIFIED, "Notification"),
        (TYPE_ASSIETTE_MODIFIED, "Modification de l'assiette"),
        (TYPE_DOTATION_ADDED, "Ajout de dotation"),
        (TYPE_DOTATION_REMOVED, "Suppression de dotation"),
        (TYPE_MONTANT_MODIFIED, "Modification du montant"),
        (TYPE_BOOLEAN_MODIFIED, "Modification de booléen"),
        (TYPE_DEPOT_DOSSIER, "Dépôt du dossier"),
        (TYPE_PASSAGE_EN_INSTRUCTION, "Passage en instruction"),
        (TYPE_RETOUR_EN_CONSTRUCTION, "Retour en construction"),
        (TYPE_RETOUR_EN_INSTRUCTION, "Retour en instruction"),
        (TYPE_DEACTIVATION, "Désactivation du dossier"),
        (TYPE_REACTIVATION, "Réactivation du dossier"),
    ]

    projet = models.ForeignKey(
        "gsl_projet.Projet",
        on_delete=models.CASCADE,
        related_name="actions",
    )
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    created_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(
        "gsl_core.Collegue",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    enveloppe = models.ForeignKey(
        "gsl_programmation.Enveloppe",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    source = models.CharField(max_length=20, choices=SOURCES)
    source_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Identifiant externe",
        help_text=(
            "Identifiant de l'événement source (ex : id du Traitement DN), "
            "pour éviter les doublons lors d'une resynchronisation."
        ),
    )
    dotation = models.CharField(
        max_length=10, choices=DOTATION_CHOICES, blank=True, default=""
    )

    status = models.CharField(max_length=50, blank=True, default="")
    euro_field_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    document_name = models.CharField(max_length=200, blank=True, default="")
    boolean_field = models.CharField(max_length=200, blank=True, default="")
    boolean_value = models.BooleanField(null=True, blank=True)
    form_id = models.CharField(max_length=200, blank=True, default="")
    details = models.TextField(blank=True, default="")
    document = models.FileField(
        upload_to=projet_action_document_upload_to, null=True, blank=True
    )

    objects = ProjetActionManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Action sur projet"
        verbose_name_plural = "Actions sur projets"

    def __str__(self):
        return f"{self.get_action_type_display()} — projet {self.projet_id}"

    @property
    def actor_name(self):
        if self.actor_id is None:
            return "Démarches Numériques"
        return self.actor.get_full_name() or self.actor.email

    @property
    def status_label(self):
        from gsl.simulation.templatetags.simulation_filters import STATUS_LABELS

        return STATUS_LABELS.get(self.status, self.status or "")

    @property
    def _status_change_label(self):
        from datetime import date

        label = f"Statut : {self.status_label}"
        if self.enveloppe_id and self.enveloppe.annee != date.today().year:
            label += f" (enveloppe {self.enveloppe.annee})"
        return label

    @property
    def action_label(self):
        doc = self.document_name.lower() if self.document_name else ""
        labels = {
            self.TYPE_STATUS_CHANGE: self._status_change_label,
            self.TYPE_DOC_GENERATED: f"Génération : {doc}",
            self.TYPE_DOC_MODIFIED: f"Modification : {doc}",
            self.TYPE_DOC_DELETED: f"Suppression : {doc}",
            self.TYPE_DOC_UPLOADED: f"Import {doc}",
            self.TYPE_DOC_UPLOAD_DELETED: f"Suppression : {doc}",
            self.TYPE_NOTIFIED: "Notification envoyée",
            self.TYPE_ASSIETTE_MODIFIED: "Modification de l'assiette",
            self.TYPE_DOTATION_ADDED: f"Ajout dotation {self.dotation}",
            self.TYPE_DOTATION_REMOVED: f"Suppression dotation {self.dotation}",
            self.TYPE_MONTANT_MODIFIED: "Modification du montant",
            self.TYPE_BOOLEAN_MODIFIED: self.boolean_field or "Modification booléen",
            self.TYPE_DEPOT_DOSSIER: "Dépôt du dossier",
            self.TYPE_PASSAGE_EN_INSTRUCTION: "Passage en instruction",
            self.TYPE_RETOUR_EN_CONSTRUCTION: "Retour en construction",
            self.TYPE_RETOUR_EN_INSTRUCTION: "Retour en instruction",
            self.TYPE_DEACTIVATION: self._deactivation_label,
            self.TYPE_REACTIVATION: "Réactivation du dossier",
        }
        return labels.get(self.action_type, self.get_action_type_display())

    @property
    def _deactivation_label(self):
        labels = {
            "archive": "Dossier archivé",
            "corbeille": "Dossier mis à la corbeille",
            "supprime": "Dossier supprimé",
        }
        return labels.get(self.details, "Désactivation du dossier")

    @property
    def precision_display(self):
        if self.euro_field_value is not None:
            from gsl_core.templatetags.gsl_filters import euro

            return euro(self.euro_field_value)
        if self.boolean_value is not None:
            return "Oui" if self.boolean_value else "Non"
        return ""


class CollegueLogEntry(LogEntry):
    class Meta:
        proxy = True
        app_label = "gsl_historique"
        verbose_name = "Entrée d'historique utilisateur"
        verbose_name_plural = "Entrées d'historique des utilisateurs"

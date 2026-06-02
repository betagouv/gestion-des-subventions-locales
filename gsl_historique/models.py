from django.db import models

from gsl_projet.constants import DOTATION_CHOICES

STATUS_LABELS = {
    "accepted": "Accepté",
    "refused": "Refusé",
    "processing": "En traitement",
    "dismissed": "Classé sans suite",
    "valid": "Accepté",
    "cancelled": "Refusé",
    "draft": "En traitement",
    "provisionally_accepted": "Accepté provisoirement",
    "provisionally_refused": "Refusé provisoirement",
}


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
    ]

    projet = models.ForeignKey(
        "gsl_projet.Projet",
        on_delete=models.CASCADE,
        related_name="actions",
    )
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
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
    dotation = models.CharField(
        max_length=10, choices=DOTATION_CHOICES, blank=True, default=""
    )

    status = models.CharField(max_length=50, blank=True, default="")
    montant = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    document_name = models.CharField(max_length=200, blank=True, default="")
    boolean_field = models.CharField(max_length=200, blank=True, default="")
    boolean_value = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Action sur projet"
        verbose_name_plural = "Actions sur projets"

    def __str__(self):
        return f"{self.get_action_type_display()} — projet {self.projet_id}"

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status or "")

    @property
    def action_label(self):
        doc = self.document_name
        labels = {
            self.TYPE_STATUS_CHANGE: f"Statut : {self.status_label}",
            self.TYPE_DOC_GENERATED: f"Export {doc}",
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
        }
        return labels.get(self.action_type, self.get_action_type_display())

    @property
    def precision_display(self):
        if self.montant is not None:
            from gsl_core.templatetags.gsl_filters import euro

            return euro(self.montant)
        if self.boolean_value is not None:
            return "Oui" if self.boolean_value else "Non"
        return ""

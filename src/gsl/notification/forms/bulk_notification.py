from django import forms
from django.db.models import Prefetch
from dsfr.forms import DsfrBaseForm

from gsl.core.models import BulkActionsJob
from gsl.notification.forms.bulk_generation import EnveloppeProjetMultipleChoiceField
from gsl.programmation.constants import BulkAction
from gsl.projet.constants import NotificationStatus, ProjetStatus
from gsl.projet.models import EnveloppeProjet


class BaseNotifyLaunchForm(DsfrBaseForm, forms.Form):
    """
    Validates the trigger button POST: keeps the projets checked in the list
    that are still notifiable for the campagne of their row.
    """

    action: BulkAction
    notified_statuses: tuple[ProjetStatus, ...]
    ids = EnveloppeProjetMultipleChoiceField(
        queryset=EnveloppeProjet.objects.none(),
        required=False,
    )

    def __init__(self, *args, user, dotation, **kwargs):
        super().__init__(*args, **kwargs)
        # Scoped by permission only: a projet whose state changed since the
        # page was loaded is left to applies_to, which counts it as skipped.
        self.fields["ids"].queryset = (
            EnveloppeProjet.objects.visible_to_user(user)
            .for_dotation(dotation)
            .select_related("projet")
            .prefetch_related(
                Prefetch(
                    "projet__enveloppeprojet_set",
                    queryset=EnveloppeProjet.objects.annotate_notification_status(),
                )
            )
        )

    @classmethod
    def applies_to(cls, enveloppe_projet) -> bool:
        projet = enveloppe_projet.projet
        # Projet.notify() only knows its most recent campagne.
        campagne = enveloppe_projet.enveloppe.annee
        return (
            projet.to_notify
            and campagne == projet.most_recent_campagne
            and projet.status_for(campagne) in cls.notified_statuses
        )

    def clean_ids(self):
        selected = self.cleaned_data["ids"]
        notifiable = [
            enveloppe_projet
            for enveloppe_projet in selected
            if self.applies_to(enveloppe_projet)
        ]
        if not notifiable:
            raise forms.ValidationError("Aucun projet à notifier.", code="no_projects")
        self.cleaned_data["skipped_count"] = len(selected) - len(notifiable)
        return notifiable


class NotifyRefusLaunchForm(BaseNotifyLaunchForm):
    action = BulkAction.NOTIFY_REFUS
    notified_statuses = ProjetStatus.NEGATIVE


class NotifyAcceptedLaunchForm(BaseNotifyLaunchForm):
    action = BulkAction.NOTIFY_ACCEPTED
    notified_statuses = (ProjetStatus.ACCEPTED,)

    @classmethod
    def applies_to(cls, enveloppe_projet) -> bool:
        campagne = enveloppe_projet.enveloppe.annee
        projet = enveloppe_projet.projet
        return super().applies_to(enveloppe_projet) and all(
            ep.notification_status == NotificationStatus.TO_NOTIFY
            for ep in projet.enveloppeprojet_set.all()
            if ep.enveloppe.annee == campagne and ep.status == ProjetStatus.ACCEPTED
        )


class NotifyMessageForm(DsfrBaseForm, forms.Form):
    message = forms.CharField(
        label="Message de notification",
        help_text="Le même message est envoyé à chacun des demandeurs.",
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    def __init__(self, *args, user, action, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.action = action
        self.fields["message"].required = action != BulkAction.NOTIFY_ACCEPTED

    def save(self, enveloppe_projets) -> BulkActionsJob:
        return BulkActionsJob.objects.create(
            action=self.action,
            created_by=self.user,
            object_ids=sorted({ep.projet_id for ep in enveloppe_projets}),
            params={"motivation": self.cleaned_data["message"]},
        )

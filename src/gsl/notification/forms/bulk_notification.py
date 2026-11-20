from django import forms
from dsfr.forms import DsfrBaseForm

from gsl.core.models import BulkActionsJob
from gsl.notification.forms.bulk_generation import EnveloppeProjetMultipleChoiceField
from gsl.programmation.constants import BulkAction
from gsl.projet.models import EnveloppeProjet


class NotifyRefusLaunchForm(DsfrBaseForm, forms.Form):
    """
    Validates the trigger button POST: the run applies to the projets checked
    in the list whose every dotation is refused or dismissed.
    """

    action = BulkAction.NOTIFY_REFUS
    ids = EnveloppeProjetMultipleChoiceField(
        queryset=EnveloppeProjet.objects.none(),
        required=False,
    )

    def __init__(self, *args, user, dotation, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["ids"].queryset = (
            EnveloppeProjet.objects.programmees()
            .active()
            .visible_to_user(user)
            .for_dotation(dotation)
            .select_related("projet")
            .prefetch_related("projet__enveloppeprojet_set")
        )

    @staticmethod
    def applies_to(enveloppe_projet) -> bool:
        projet = enveloppe_projet.projet
        return projet.to_notify and not projet.has_accepted_dotation

    def clean_ids(self):
        eligible = [
            enveloppe_projet
            for enveloppe_projet in self.cleaned_data.get("ids") or []
            if self.applies_to(enveloppe_projet)
        ]
        if not eligible:
            raise forms.ValidationError("Aucun projet à notifier.", code="no_projects")
        return eligible


class NotifyRefusMessageForm(DsfrBaseForm, forms.Form):
    message = forms.CharField(
        label="Motivation",
        help_text="Le même message est envoyé à chacun des demandeurs.",
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def save(self, enveloppe_projets) -> BulkActionsJob:
        return BulkActionsJob.objects.create(
            action=BulkAction.NOTIFY_REFUS,
            created_by=self.user,
            object_ids=sorted({ep.projet_id for ep in enveloppe_projets}),
            params={"motivation": self.cleaned_data["message"]},
        )

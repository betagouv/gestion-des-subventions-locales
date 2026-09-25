import os

from django import forms
from django.db import transaction
from dsfr.forms import DsfrBaseForm

from gsl.notification.utils import merge_documents_into_pdf
from gsl.projet.constants import DOTATIONS, ProjetStatus
from gsl.projet.models import Projet
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService


class NotificationMessageForm(DsfrBaseForm, forms.ModelForm):
    message = forms.CharField(
        label="Message de notification",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    class Meta:
        model = Projet
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.status != ProjetStatus.ACCEPTED:
            self.fields["message"].required = True

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.enveloppeprojet_set.without_signed_document().exists():
            raise forms.ValidationError(
                "Impossible d'envoyer la notification : il manque des documents "
                "signés obligatoires."
            )
        return cleaned_data

    def save(self, user):
        documents = self.instance.imported_documents
        justificatif_file = None
        if documents:
            filename = self._notification_filename(documents)
            justificatif_file = merge_documents_into_pdf(documents, filename=filename)

        # Dossier was recently refreshed DN
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
        if self.instance.dossier_ds.ds_state == Dossier.STATE_EN_CONSTRUCTION:
            ds = DsService()
            ds.passer_en_instruction(dossier=self.instance.dossier_ds, user=user)

        status = self.instance.status
        motivation = self.cleaned_data.get("message", "")

        with transaction.atomic():
            ds_service = DsService()

            if status == ProjetStatus.ACCEPTED:
                ds_service.accept_in_ds(
                    self.instance.dossier_ds,
                    user,
                    document=justificatif_file,
                    motivation=motivation,
                )
            elif status == ProjetStatus.DISMISSED:
                ds_service.dismiss_in_ds(
                    self.instance.dossier_ds,
                    user,
                    motivation=motivation,
                    document=justificatif_file,
                )
            else:
                ds_service.refuser_in_ds(
                    self.instance.dossier_ds,
                    user,
                    motivation=motivation,
                    document=justificatif_file,
                )
            return self.instance

    def _notification_filename(self, documents):
        if len(documents) <= 1:
            return os.path.splitext(documents[0].name)[0] + ".pdf"
        dotations = {doc.enveloppe_projet.dotation for doc in documents}
        ordered = [d for d in DOTATIONS if d in dotations]
        ds_number = self.instance.dossier_ds.ds_number
        return f"Notification {ds_number} {'-'.join(ordered)}.pdf"

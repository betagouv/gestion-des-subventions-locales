import os

from django.db import transaction

from gsl.core.models import Collegue
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService

from ..constants import DOTATIONS, ProjetStatus
from ..utils.utils import merge_documents_into_pdf


class ProjetDNActionsMixin:
    """
    Actions of a Projet that go through Démarches Numériques.
    """

    def notify(self, user: Collegue, motivation: str = "") -> None:
        documents = self.imported_documents
        justificatif_file = None
        if documents:
            justificatif_file = merge_documents_into_pdf(
                documents, filename=self._notification_filename(documents)
            )

        ds_service = DsService()
        # Dossier was recently refreshed DN
        # Race conditions remain possible, but should be rare enough and just fail without any side effect.
        if self.dossier_ds.ds_state == Dossier.State.EN_CONSTRUCTION:
            ds_service.passer_en_instruction(dossier=self.dossier_ds, user=user)

        notify_in_ds = {
            ProjetStatus.ACCEPTED: ds_service.accepter,
            ProjetStatus.REFUSED: ds_service.refuser,
            ProjetStatus.DISMISSED: ds_service.classer_sans_suite,
        }[self.status]
        with transaction.atomic():
            notify_in_ds(
                self.dossier_ds,
                user,
                motivation=motivation,
                document=justificatif_file,
            )

    def _notification_filename(self, documents) -> str:
        if len(documents) <= 1:
            return os.path.splitext(documents[0].name)[0] + ".pdf"
        dotations = {doc.enveloppe_projet.dotation for doc in documents}
        ordered = [d for d in DOTATIONS if d in dotations]
        return f"Notification {self.dossier_ds.ds_number} {'-'.join(ordered)}.pdf"

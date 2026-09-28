from contextlib import ExitStack, contextmanager
from unittest import mock

import pytest

from gsl.core.tests.factories import CollegueFactory
from gsl.notification.tests.factories import LettreEtArreteSignesFactory
from gsl_demarches_simplifiees.models import Dossier

from ...constants import DOTATION_DETR, ProjetStatus
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


DS_NOTIFY_METHODS = ("accept_in_ds", "refuser_in_ds", "dismiss_in_ds")


@pytest.mark.parametrize(
    ("status", "expected_method"),
    (
        (ProjetStatus.ACCEPTED, "accept_in_ds"),
        (ProjetStatus.REFUSED, "refuser_in_ds"),
        (ProjetStatus.DISMISSED, "dismiss_in_ds"),
    ),
)
def test_notify_calls_the_ds_method_matching_projet_status(status, expected_method):
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION)
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR, status=status)
    user = CollegueFactory()

    with _patch_ds_notify_methods() as mocks:
        projet.notify(user, motivation="Motif")

    for method, method_mock in mocks.items():
        if method == expected_method:
            method_mock.assert_called_once_with(
                projet.dossier_ds, user, motivation="Motif", document=None
            )
        else:
            method_mock.assert_not_called()


def test_notify_merges_imported_documents_into_one_pdf():
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION)
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)
    merged_pdf = mock.sentinel.merged_pdf

    with (
        _patch_ds_notify_methods() as mocks,
        mock.patch(
            "gsl.projet.mixins.merge_documents_into_pdf", return_value=merged_pdf
        ) as merge_mock,
    ):
        projet.notify(CollegueFactory())

    assert merge_mock.call_args.args[0] == projet.imported_documents
    assert mocks["accept_in_ds"].call_args.kwargs["document"] is merged_pdf


def test_notify_without_imported_documents_does_not_merge():
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.REFUSED
    )

    with (
        _patch_ds_notify_methods(),
        mock.patch("gsl.projet.mixins.merge_documents_into_pdf") as merge_mock,
    ):
        projet.notify(CollegueFactory(), motivation="Motif")

    merge_mock.assert_not_called()


@pytest.mark.parametrize(
    ("ds_state", "expected_passer_en_instruction"),
    (
        (Dossier.State.EN_CONSTRUCTION, True),
        (Dossier.State.EN_INSTRUCTION, False),
    ),
)
def test_notify_passes_dossier_en_instruction_only_when_en_construction(
    ds_state, expected_passer_en_instruction
):
    projet = ProjetFactory(dossier_ds__ds_state=ds_state)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.REFUSED
    )
    user = CollegueFactory()

    with (
        _patch_ds_notify_methods(),
        mock.patch(
            "gsl_demarches_simplifiees.services.DsService.passer_en_instruction"
        ) as passer_en_instruction,
    ):
        projet.notify(user, motivation="Motif")

    if expected_passer_en_instruction:
        passer_en_instruction.assert_called_once_with(
            dossier=projet.dossier_ds, user=user
        )
    else:
        passer_en_instruction.assert_not_called()


def test_notify_raises_on_processing_projet():
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.State.EN_INSTRUCTION)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )

    with _patch_ds_notify_methods() as mocks, pytest.raises(KeyError):
        projet.notify(CollegueFactory())

    for method_mock in mocks.values():
        method_mock.assert_not_called()


@contextmanager
def _patch_ds_notify_methods():
    """Patches every DsService notification method, yielding {name: mock}."""
    with ExitStack() as stack:
        yield {
            method: stack.enter_context(
                mock.patch(f"gsl_demarches_simplifiees.services.DsService.{method}")
            )
            for method in DS_NOTIFY_METHODS
        }

from contextlib import ExitStack, contextmanager
from unittest import mock

import pytest
from django.utils import timezone

from gsl.core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl.notification.tests.factories import (
    AnnexeFactory,
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    LettreRefusSigneeFactory,
)
from gsl_demarches_simplifiees.models import Dossier

from ...constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ...models import Projet
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    (
        "create_a_detr_projet",
        "create_a_dsil_projet",
        "demande_montant",
        "expected_can_have_a_commission_detr_avis",
    ),
    (
        (True, False, 100_000, True),
        (True, False, 99_999, False),
        (True, False, None, False),
        (True, True, 100_000, True),
        (True, True, 99_999, False),
        (True, True, None, False),
        (False, True, 100_000, False),
        (False, True, 99_999, False),
        (False, True, None, False),
    ),
)
def test_can_have_a_commission_detr_avis(
    create_a_detr_projet,
    create_a_dsil_projet,
    demande_montant,
    expected_can_have_a_commission_detr_avis,
):
    projet = ProjetFactory(dossier_ds__demande_montant=demande_montant)
    if create_a_detr_projet:
        EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    if create_a_dsil_projet:
        EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    assert (
        projet.can_have_a_commission_detr_avis
        is expected_can_have_a_commission_detr_avis
    )


def test_has_double_dotations():
    projet = ProjetFactory()
    assert projet.has_double_dotations is False

    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.has_double_dotations is False

    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.has_double_dotations is True


def test_dotation_detr():
    projet = ProjetFactory()
    assert projet.dotation_detr is None

    dotation = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.dotation_detr is None

    dotation = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.dotation_detr == dotation


def test_dotation_dsil():
    projet = ProjetFactory()
    assert projet.dotation_dsil is None

    dotation = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.dotation_dsil is None

    dotation = EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.dotation_dsil == dotation


@pytest.mark.parametrize(
    ("notified_at", "expected_has_been_notified"),
    (
        (None, False),
        (timezone.now(), True),
    ),
)
def test_has_been_notified(notified_at, expected_has_been_notified):
    projet = ProjetFactory(notified_at=notified_at)
    assert projet.has_been_notified is expected_has_been_notified


def test_to_notify_false_without_enveloppe_projet():
    """Project without any EnveloppeProjet should return False."""
    projet = ProjetFactory()
    assert projet.to_notify is False
    assert projet not in Projet.objects.to_notify()


def test_to_notify_false_with_prcessing_enveloppe_projet():
    """Project without any programmation should return False."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )

    assert projet.to_notify is False


@pytest.mark.parametrize(
    "status", (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED)
)
def test_to_notify_true_with_treated_enveloppe_projet(status):
    """Project with programmation but not notified should return True."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR, status=status)
    assert projet.to_notify is True


def test_to_notify_false_when_projet_already_notified():
    """Project already notified should return False."""
    projet = ProjetFactory(notified_at=timezone.now())
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )

    assert projet.to_notify is False


def test_to_notify_with_double_dotation_all_notified():
    """Double dotation project returns False only if all dotations are notified."""
    projet = ProjetFactory(notified_at=timezone.now())
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.ACCEPTED
    )

    assert projet.to_notify is False


def test_to_notify_with_double_dotation_partial_programmation():
    """Double dotation project returns False if any dotation lacks programmation."""
    projet = ProjetFactory(notified_at=None)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.PROCESSING
    )

    assert projet.to_notify is False


def test_with_at_least_one_treated_dotation():
    """Project with at least one accepted programmation should be included."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_without_programmation():
    """Project without programmation should not be included."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 0
    assert projet not in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_with_refused_status():
    """Project with a refused programmation should be included."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.REFUSED
    )
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_with_dismissed_status():
    """Project with a dismissed programmation should be included."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.DISMISSED
    )
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_when_projet_has_two_accepted_programmations():
    """Project with two accepted programmations should be included once."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.ACCEPTED
    )
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_with_one_accepted_one_refused():
    """Project with one accepted and one refused programmation should be included."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.REFUSED
    )
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_for_user():
    """Test with_at_least_one_treated_dotation combined with for_user filter."""
    perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )

    projet_not_in_perimeter = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet_not_in_perimeter,
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
    )

    assert (
        Projet.objects.for_user(user).with_at_least_one_treated_dotation().count() == 1
    )
    assert projet in Projet.objects.for_user(user).with_at_least_one_treated_dotation()
    assert (
        projet_not_in_perimeter
        not in Projet.objects.for_user(user).with_at_least_one_treated_dotation()
    )


def test_can_display_notification_tab_without_dotations():
    """Project without any dotations should return False."""
    projet = ProjetFactory()
    assert projet.can_display_notification_tab is False


def test_can_display_notification_tab_with_accepted_dotation():
    """Project with processing dotation should return False."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    assert projet.can_display_notification_tab is True


def test_can_display_notification_tab_with_processing_dotation():
    """Project with only a processing dotation should return False."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )
    assert projet.can_display_notification_tab is False


@pytest.mark.parametrize(
    "dotation_status",
    [ProjetStatus.REFUSED, ProjetStatus.DISMISSED],
)
def test_can_display_notification_tab_with_refused_or_dismissed_dotation(
    dotation_status,
):
    """Refused/dismissed dotations are treated too: the notification tab is
    where the "À notifier" action for them lives."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_status
    )
    assert projet.can_display_notification_tab is True


@pytest.mark.parametrize(
    "first_dotation_status, second_dotation_status, expected_can_display_notification_tab",
    [
        (ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED, True),
        (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, True),
        (ProjetStatus.ACCEPTED, ProjetStatus.DISMISSED, True),
        (ProjetStatus.ACCEPTED, ProjetStatus.PROCESSING, True),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED, True),
        (ProjetStatus.REFUSED, ProjetStatus.DISMISSED, True),
        (ProjetStatus.REFUSED, ProjetStatus.PROCESSING, True),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED, True),
        (ProjetStatus.DISMISSED, ProjetStatus.PROCESSING, True),
        (ProjetStatus.PROCESSING, ProjetStatus.PROCESSING, False),
    ],
)
def test_can_display_notification_tab_with_multiple_dotations(
    first_dotation_status, second_dotation_status, expected_can_display_notification_tab
):
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=first_dotation_status
    )
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=second_dotation_status
    )
    assert projet.can_display_notification_tab is expected_can_display_notification_tab


def test_dotation_not_treated_without_dotations():
    """Project without any dotations should return None."""
    projet = ProjetFactory()
    assert projet.dotation_not_treated is None


def test_dotation_not_treated_with_processing_dotation():
    """Project with processing dotation should return that dotation."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )
    assert projet.dotation_not_treated == DOTATION_DETR


@pytest.mark.parametrize(
    "dotation_status",
    [ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED],
)
def test_dotation_not_treated_with_not_processing_dotation(dotation_status):
    """Project with non-processing dotation should return None."""
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=dotation_status
    )
    assert projet.dotation_not_treated is None


@pytest.mark.parametrize(
    "first_status, second_status, expected_dotation_not_treated",
    [
        (ProjetStatus.ACCEPTED, ProjetStatus.PROCESSING, DOTATION_DSIL),
        (ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED, DOTATION_DETR),
        (
            ProjetStatus.PROCESSING,
            ProjetStatus.PROCESSING,
            DOTATION_DETR,
        ),  # Should return the first one encountered (DETR)
    ],
)
def test_dotation_not_treated_with_multiple_dotations_one_processing(
    first_status, second_status, expected_dotation_not_treated
):
    projet = ProjetFactory()
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR, status=first_status)
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL, status=second_status)
    assert projet.dotation_not_treated == expected_dotation_not_treated


@pytest.mark.parametrize(
    "status, expected_value",
    (
        (ProjetStatus.ACCEPTED, False),
        (ProjetStatus.REFUSED, False),
        (ProjetStatus.DISMISSED, False),
        (ProjetStatus.PROCESSING, True),
    ),
)
def test_all_dotations_have_processing_status_when_simple_dotation(
    status, expected_value
):
    projet = ProjetFactory()
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR, status=status)
    assert projet.all_dotations_have_processing_status is expected_value


@pytest.mark.parametrize(
    "first_status, second_status, expected_value",
    (
        (ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED, False),
        (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, False),
        (ProjetStatus.ACCEPTED, ProjetStatus.DISMISSED, False),
        (ProjetStatus.ACCEPTED, ProjetStatus.PROCESSING, False),
        (ProjetStatus.REFUSED, ProjetStatus.REFUSED, False),
        (ProjetStatus.REFUSED, ProjetStatus.DISMISSED, False),
        (ProjetStatus.REFUSED, ProjetStatus.PROCESSING, False),
        (ProjetStatus.DISMISSED, ProjetStatus.DISMISSED, False),
        (ProjetStatus.DISMISSED, ProjetStatus.PROCESSING, False),
        (ProjetStatus.PROCESSING, ProjetStatus.PROCESSING, True),
    ),
)
def test_all_dotations_have_processing_status_when_double_dotations(
    first_status, second_status, expected_value
):
    projet = ProjetFactory()
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DETR, status=first_status)
    EnveloppeProjetFactory(projet=projet, dotation=DOTATION_DSIL, status=second_status)
    assert projet.all_dotations_have_processing_status is expected_value


def test_zonage_and_contracts_provided_by_instructor_empty():
    """Project with no zonage or contract fields set should return empty list."""
    projet = ProjetFactory()
    assert projet.areas_and_contracts_provided_by_instructor == []


def test_zonage_and_contracts_provided_by_instructor_single_field():
    """Project with one zonage field set should return that field's label."""
    projet = ProjetFactory(is_in_qpv=True)
    result = projet.areas_and_contracts_provided_by_instructor
    assert len(result) == 1
    assert "Projet situé en QPV" in result


def test_zonage_and_contracts_provided_by_instructor_multiple_fields():
    """Project with multiple zonage/contract fields set should return all their labels."""
    projet = ProjetFactory(
        is_in_qpv=True,
        is_attached_to_a_crte=True,
        is_frr=True,
    )
    result = projet.areas_and_contracts_provided_by_instructor
    assert len(result) == 3
    assert "Projet situé en QPV" in result
    assert "Projet rattaché à un CRTE" in result
    assert "Projet situé en FRR" in result


def test_zonage_and_contracts_provided_by_instructor_all_fields():
    """Project with all zonage/contract fields set should return all labels."""
    projet = ProjetFactory(
        is_in_qpv=True,
        is_attached_to_a_crte=True,
        is_frr=True,
        is_acv=True,
        is_pvd=True,
        is_va=True,
        is_autre_zonage_local=True,
        is_contrat_local=True,
    )
    result = projet.areas_and_contracts_provided_by_instructor
    assert len(result) == 8
    assert "Projet situé en QPV" in result
    assert "Projet rattaché à un CRTE" in result
    assert "Projet situé en FRR" in result
    assert "Projet rattaché à un programme Action coeurs de Ville (ACV)" in result
    assert "Projet rattaché à un programme Petites villes de demain (PVD)" in result
    assert "Projet rattaché à un programme Villages d'avenir" in result
    assert "Projet rattaché à un autre zonage local" in result
    assert "Projet rattaché à un contrat local" in result


def test_zonage_and_contracts_provided_by_instructor_excludes_false_fields():
    """Project should only include fields that are True, not False."""
    projet = ProjetFactory(
        is_in_qpv=True,
        is_attached_to_a_crte=False,
        is_frr=True,
        is_acv=False,
    )
    result = projet.areas_and_contracts_provided_by_instructor
    assert len(result) == 2
    assert "Projet situé en QPV" in result
    assert "Projet situé en FRR" in result
    assert "Projet rattaché à un CRTE" not in result
    assert "Projet rattaché à un programme Action coeurs de Ville (ACV)" not in result


def test_zonage_and_contracts_provided_by_instructor_excludes_other_fields():
    """Project should not include is_budget_vert even if True."""
    projet = ProjetFactory(
        is_in_qpv=True,
        is_budget_vert=True,  # This field is not in the list
    )
    result = projet.areas_and_contracts_provided_by_instructor
    assert len(result) == 1
    assert "Projet situé en QPV" in result
    assert (
        "Projet concourant à la transition écologique au sens budget vert" not in result
    )


def test_generated_documents_sorted_by_dotation_then_type():
    projet = ProjetFactory()
    detr_dp = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    dsil_dp = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.ACCEPTED
    )
    # Created in a deliberately mixed order to prove the sort, not the creation order.
    lettre_dsil = LettreNotificationFactory(enveloppe_projet=dsil_dp)
    arrete_dsil = ArreteFactory(enveloppe_projet=dsil_dp)
    lettre_detr = LettreNotificationFactory(enveloppe_projet=detr_dp)
    arrete_detr = ArreteFactory(enveloppe_projet=detr_dp)

    assert projet.generated_documents == [
        arrete_detr,
        lettre_detr,
        arrete_dsil,
        lettre_dsil,
    ]


def test_imported_documents_sorted_by_dotation_then_type_with_annexe_last():
    projet = ProjetFactory()
    detr_dp = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    dsil_dp = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.ACCEPTED
    )
    # Created in a deliberately mixed order to prove the sort, not the creation order.
    annexe_dsil = AnnexeFactory(enveloppe_projet=dsil_dp)
    lettre_et_arrete_signes_dsil = LettreEtArreteSignesFactory(enveloppe_projet=dsil_dp)
    annexe_detr = AnnexeFactory(enveloppe_projet=detr_dp)
    lettre_et_arrete_signes_detr = LettreEtArreteSignesFactory(enveloppe_projet=detr_dp)

    assert projet.imported_documents == [
        lettre_et_arrete_signes_detr,
        annexe_detr,
        lettre_et_arrete_signes_dsil,
        annexe_dsil,
    ]


@pytest.mark.django_db
def test_imported_documents_includes_signed_refusal_letter():
    projet = ProjetFactory()
    accepted_dp = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    refused_dp = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.REFUSED
    )
    lettre_et_arrete_signes = LettreEtArreteSignesFactory(enveloppe_projet=accepted_dp)
    lettre_refus_signee = LettreRefusSigneeFactory(enveloppe_projet=refused_dp)

    assert projet.imported_documents == [
        lettre_et_arrete_signes,
        lettre_refus_signee,
    ]


# Projet.notify ========================================================================

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
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION)
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
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION)
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)
    merged_pdf = mock.sentinel.merged_pdf

    with (
        _patch_ds_notify_methods() as mocks,
        mock.patch(
            "gsl.projet.models.merge_documents_into_pdf", return_value=merged_pdf
        ) as merge_mock,
    ):
        projet.notify(CollegueFactory())

    assert merge_mock.call_args.args[0] == projet.imported_documents
    assert mocks["accept_in_ds"].call_args.kwargs["document"] is merged_pdf


def test_notify_without_imported_documents_does_not_merge():
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION)
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.REFUSED
    )

    with (
        _patch_ds_notify_methods(),
        mock.patch("gsl.projet.models.merge_documents_into_pdf") as merge_mock,
    ):
        projet.notify(CollegueFactory(), motivation="Motif")

    merge_mock.assert_not_called()


@pytest.mark.parametrize(
    ("ds_state", "expected_passer_en_instruction"),
    (
        (Dossier.STATE_EN_CONSTRUCTION, True),
        (Dossier.STATE_EN_INSTRUCTION, False),
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
    projet = ProjetFactory(dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION)
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

import pytest

from gsl_core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    LettreRefusSigneeFactory,
)
from gsl_programmation.models import ProgrammationProjet as pp
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

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
        DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    if create_a_dsil_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    assert (
        projet.can_have_a_commission_detr_avis
        is expected_can_have_a_commission_detr_avis
    )


def test_has_double_dotations():
    projet = ProjetFactory()
    assert projet.has_double_dotations is False

    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.has_double_dotations is False

    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.has_double_dotations is True


def test_dotation_detr():
    projet = ProjetFactory()
    assert projet.dotation_detr is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.dotation_detr is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.dotation_detr == dotation


def test_dotation_dsil():
    projet = ProjetFactory()
    assert projet.dotation_dsil is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert projet.dotation_dsil is None

    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    assert projet.dotation_dsil == dotation


def test_to_notify_false_without_dotation_projet():
    """Project without any DotationProjet should return False."""
    projet = ProjetFactory()
    assert projet.to_notify is False
    assert projet not in Projet.objects.to_notify()


def test_to_notify_false_with_prcessing_dotation_projet():
    """Project without any programmation should return False."""
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )

    assert projet.to_notify is False


@pytest.mark.parametrize(
    "status", (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED)
)
def test_to_notify_true_with_treated_dotation_projet(status):
    """Project with programmation but not notified should return True."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=status)
    assert projet.to_notify is True


def test_to_notify_false_when_projet_already_notified():
    """Project already notified should return False."""
    from django.utils import timezone

    projet = ProjetFactory(notified_at=timezone.now())
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

    ProgrammationProjetFactory(dotation_projet=dotation)
    assert projet.to_notify is False


def test_to_notify_with_double_dotation_all_notified():
    """Double dotation project returns False only if all dotations are notified."""
    from django.utils import timezone

    projet = ProjetFactory(notified_at=timezone.now())
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    ProgrammationProjetFactory(dotation_projet=dotation_detr)
    ProgrammationProjetFactory(dotation_projet=dotation_dsil)

    assert projet.to_notify is False


def test_to_notify_with_double_dotation_partial_programmation():
    """Double dotation project returns False if any dotation lacks programmation."""
    projet = ProjetFactory(notified_at=None)
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
    )

    assert projet.to_notify is False


def test_with_at_least_one_treated_dotation():
    """Project with at least one accepted programmation should be included."""
    projet = ProjetFactory()
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(dotation_projet=dotation, status=pp.STATUS_ACCEPTED)
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_without_programmation():
    """Project without programmation should not be included."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 0
    assert projet not in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_with_refused_status():
    """Project with a refused programmation should be included."""
    projet = ProjetFactory()
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(dotation_projet=dotation, status=pp.STATUS_REFUSED)
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_with_dismissed_status():
    """Project with a dismissed programmation should be included."""
    projet = ProjetFactory()
    dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(dotation_projet=dotation, status=pp.STATUS_DISMISSED)
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_when_projet_has_two_accepted_programmations():
    """Project with two accepted programmations should be included once."""
    projet = ProjetFactory()
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    ProgrammationProjetFactory(dotation_projet=dotation_detr, status=pp.STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dotation_dsil, status=pp.STATUS_ACCEPTED)
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_with_one_accepted_one_refused():
    """Project with one accepted and one refused programmation should be included."""
    projet = ProjetFactory()
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    ProgrammationProjetFactory(dotation_projet=dotation_detr, status=pp.STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dotation_dsil, status=pp.STATUS_REFUSED)
    assert Projet.objects.with_at_least_one_treated_dotation().count() == 1
    assert projet in Projet.objects.with_at_least_one_treated_dotation()


def test_with_at_least_one_treated_dotation_for_user():
    """Test with_at_least_one_treated_dotation combined with for_user filter."""
    perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dotation_detr = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(dotation_projet=dotation_detr, status=pp.STATUS_ACCEPTED)

    projet_not_in_perimeter = ProjetFactory()
    dotation_detr_not_in_perimeter = DotationProjetFactory(
        projet=projet_not_in_perimeter, dotation=DOTATION_DETR
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_detr_not_in_perimeter,
        status=pp.STATUS_ACCEPTED,
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
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    assert projet.can_display_notification_tab is True


def test_can_display_notification_tab_with_processing_dotation():
    """Project with only a processing dotation should return False."""
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    assert projet.can_display_notification_tab is False


@pytest.mark.parametrize(
    "dotation_status",
    [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED],
)
def test_can_display_notification_tab_with_refused_or_dismissed_dotation(
    dotation_status,
):
    """Refused/dismissed dotations are treated too: the notification tab is
    where the "À notifier" action for them lives."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=dotation_status)
    assert projet.can_display_notification_tab is True


@pytest.mark.parametrize(
    "first_dotation_status, second_dotation_status, expected_can_display_notification_tab",
    [
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING, True),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_PROCESSING, False),
    ],
)
def test_can_display_notification_tab_with_multiple_dotations(
    first_dotation_status, second_dotation_status, expected_can_display_notification_tab
):
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=first_dotation_status
    )
    DotationProjetFactory(
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
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    assert projet.dotation_not_treated == DOTATION_DETR


@pytest.mark.parametrize(
    "dotation_status",
    [PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED],
)
def test_dotation_not_treated_with_not_processing_dotation(dotation_status):
    """Project with non-processing dotation should return None."""
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=dotation_status)
    assert projet.dotation_not_treated is None


@pytest.mark.parametrize(
    "first_status, second_status, expected_dotation_not_treated",
    [
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, DOTATION_DSIL),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_ACCEPTED, DOTATION_DETR),
        (
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_PROCESSING,
            DOTATION_DETR,
        ),  # Should return the first one encountered (DETR)
    ],
)
def test_dotation_not_treated_with_multiple_dotations_one_processing(
    first_status, second_status, expected_dotation_not_treated
):
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=first_status)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL, status=second_status)
    assert projet.dotation_not_treated == expected_dotation_not_treated


@pytest.mark.parametrize(
    "status, expected_value",
    (
        (PROJET_STATUS_ACCEPTED, False),
        (PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_PROCESSING, True),
    ),
)
def test_all_dotations_have_processing_status_when_simple_dotation(
    status, expected_value
):
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=status)
    assert projet.all_dotations_have_processing_status is expected_value


@pytest.mark.parametrize(
    "first_status, second_status, expected_value",
    (
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED, False),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_ACCEPTED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_REFUSED, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_REFUSED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_DISMISSED, False),
        (PROJET_STATUS_DISMISSED, PROJET_STATUS_PROCESSING, False),
        (PROJET_STATUS_PROCESSING, PROJET_STATUS_PROCESSING, True),
    ),
)
def test_all_dotations_have_processing_status_when_double_dotations(
    first_status, second_status, expected_value
):
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR, status=first_status)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL, status=second_status)
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
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )
    detr_pp = ProgrammationProjetFactory(dotation_projet=detr_dp)
    dsil_pp = ProgrammationProjetFactory(dotation_projet=dsil_dp)

    # Created in a deliberately mixed order to prove the sort, not the creation order.
    lettre_dsil = LettreNotificationFactory(programmation_projet=dsil_pp)
    arrete_dsil = ArreteFactory(programmation_projet=dsil_pp)
    lettre_detr = LettreNotificationFactory(programmation_projet=detr_pp)
    arrete_detr = ArreteFactory(programmation_projet=detr_pp)

    assert projet.generated_documents == [
        arrete_detr,
        lettre_detr,
        arrete_dsil,
        lettre_dsil,
    ]


def test_imported_documents_sorted_by_dotation_then_type_with_annexe_last():
    projet = ProjetFactory()
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )
    detr_pp = ProgrammationProjetFactory(dotation_projet=detr_dp)
    dsil_pp = ProgrammationProjetFactory(dotation_projet=dsil_dp)

    # Created in a deliberately mixed order to prove the sort, not the creation order.
    annexe_dsil = AnnexeFactory(programmation_projet=dsil_pp)
    lettre_et_arrete_signes_dsil = LettreEtArreteSignesFactory(
        programmation_projet=dsil_pp
    )
    annexe_detr = AnnexeFactory(programmation_projet=detr_pp)
    lettre_et_arrete_signes_detr = LettreEtArreteSignesFactory(
        programmation_projet=detr_pp
    )

    assert projet.imported_documents == [
        lettre_et_arrete_signes_detr,
        annexe_detr,
        lettre_et_arrete_signes_dsil,
        annexe_dsil,
    ]


@pytest.mark.django_db
def test_imported_documents_includes_signed_refusal_letter():
    projet = ProjetFactory()
    accepted_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    refused_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_REFUSED
    )
    accepted_pp = ProgrammationProjetFactory(dotation_projet=accepted_dp)
    refused_pp = ProgrammationProjetFactory(
        dotation_projet=refused_dp, status=pp.STATUS_REFUSED
    )

    lettre_et_arrete_signes = LettreEtArreteSignesFactory(
        programmation_projet=accepted_pp
    )
    lettre_refus_signee = LettreRefusSigneeFactory(programmation_projet=refused_pp)

    assert projet.imported_documents == [
        lettre_et_arrete_signes,
        lettre_refus_signee,
    ]

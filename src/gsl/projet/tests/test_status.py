import pytest
from django.utils import timezone

from dn.sync.models import Dotation
from gsl.core.campagne import get_campagne
from gsl.programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory

from ..constants import ProjetStatus
from ..models import EnveloppeProjet, Projet
from .factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def test_projet_without_enveloppe_projet_has_no_status():
    projet = ProjetFactory()
    assert projet.status_for(get_campagne()) is None


def test_update_projet_status_on_post_save():
    projet: Projet = ProjetFactory()
    enveloppe = DetrEnveloppeFactory()
    enveloppe_projet: EnveloppeProjet = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.DISMISSED,
        dotation=Dotation.DETR,
        enveloppe=enveloppe,
    )

    enveloppe_projet.save()
    assert projet.status_for(get_campagne()) == ProjetStatus.DISMISSED

    enveloppe_projet.refuse(enveloppe=enveloppe)
    enveloppe_projet.save()
    assert projet.status_for(get_campagne()) == ProjetStatus.REFUSED

    enveloppe_projet = enveloppe_projet.set_back_status_to_processing_without_ds()
    assert projet.status_for(get_campagne()) == ProjetStatus.PROCESSING

    enveloppe_projet.accept_without_ds_update(montant=1_000, enveloppe=enveloppe)
    enveloppe_projet.save()
    assert projet.status_for(get_campagne()) == ProjetStatus.ACCEPTED


def test_update_projet_status_on_post_delete():
    projet = ProjetFactory()
    accepted_enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.ACCEPTED, dotation=Dotation.DETR
    )
    EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.REFUSED, dotation=Dotation.DSIL
    )

    accepted_enveloppe_projet.delete()
    assert projet.status_for(get_campagne()) is ProjetStatus.REFUSED


@pytest.mark.parametrize(
    "accepted, processing, refused, dismissed, expected_status",
    (
        (True, False, False, False, ProjetStatus.ACCEPTED),
        (False, True, False, False, ProjetStatus.PROCESSING),
        (False, False, True, False, ProjetStatus.REFUSED),
        (False, False, False, True, ProjetStatus.DISMISSED),
        (True, True, False, False, ProjetStatus.PROCESSING),
        (True, False, True, False, ProjetStatus.ACCEPTED),
        (True, False, False, True, ProjetStatus.ACCEPTED),
        (False, True, True, False, ProjetStatus.PROCESSING),
        (False, True, False, True, ProjetStatus.PROCESSING),
        (False, False, True, True, ProjetStatus.DISMISSED),
    ),
)
def test_status_mixed_dotations(
    accepted, processing, refused, dismissed, expected_status
):
    projet = ProjetFactory()
    current_dotation = Dotation.DETR

    if accepted:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.ACCEPTED,
            dotation=current_dotation,
        )
        current_dotation = Dotation.DSIL
    if processing:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.PROCESSING,
            dotation=current_dotation,
        )
        current_dotation = Dotation.DSIL
    if refused:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.REFUSED,
            dotation=current_dotation,
        )
        current_dotation = Dotation.DSIL
    if dismissed:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.DISMISSED,
            dotation=current_dotation,
        )

    assert projet.status_for(get_campagne()) == expected_status


# Status per campagne ==================================================================


@pytest.fixture
def projet_refuse_en_2026_et_accepte_en_2027():
    projet = ProjetFactory()
    perimetre = projet.dossier_ds.perimetre
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
    )
    return projet


@pytest.mark.parametrize(
    "campagne, expected_status",
    (
        (2026, ProjetStatus.REFUSED),
        (2027, ProjetStatus.ACCEPTED),
        (2025, None),
    ),
)
def test_status_for_only_considers_the_campagne(
    projet_refuse_en_2026_et_accepte_en_2027, campagne, expected_status
):
    projet = projet_refuse_en_2026_et_accepte_en_2027

    assert projet.status_for(campagne) == expected_status
    assert (
        Projet.objects.annotate_status(campagne).get(pk=projet.pk)._status
        == expected_status
    )


# Actifs ===============================================================================


def test_enveloppe_projets_of_an_older_campagne_are_closed_notified_or_not():
    projet = ProjetFactory()
    perimetre = projet.dossier_ds.perimetre
    notifie = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        notified_at=timezone.now(),
    )
    non_notifie = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DsilEnveloppeFactory(perimetre=perimetre, annee=2026),
    )
    suivant = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
    )
    enveloppe_projets = EnveloppeProjet.objects.filter(projet=projet)

    assert list(enveloppe_projets.in_most_recent_campagne()) == [suivant]
    assert projet.enveloppe_projets_in_most_recent_campagne == [suivant]
    assert set(enveloppe_projets.closed()) == {notifie, non_notifie}


def test_a_notified_enveloppe_projet_of_the_last_campagne_is_in_most_recent_campagne():
    enveloppe_projet = EnveloppeProjetFactory(
        status=ProjetStatus.ACCEPTED, notified_at=timezone.now()
    )

    assert list(EnveloppeProjet.objects.in_most_recent_campagne()) == [enveloppe_projet]
    assert enveloppe_projet.projet.enveloppe_projets_in_most_recent_campagne == [
        enveloppe_projet
    ]


def test_a_projet_without_enveloppe_projet_has_none_in_most_recent_campagne():
    projet = ProjetFactory()

    assert projet.enveloppe_projets_in_most_recent_campagne == []


def test_a_non_courant_enveloppe_projet_is_not_in_most_recent_campagne():
    courant = EnveloppeProjetFactory(status=ProjetStatus.PROCESSING)
    EnveloppeProjetFactory(
        projet=courant.projet,
        status=ProjetStatus.REFUSED,
        enveloppe=courant.enveloppe,
        notified_at=timezone.now(),
        is_courant=False,
    )

    assert courant.projet.enveloppe_projets_in_most_recent_campagne == [courant]
    assert list(
        EnveloppeProjet.objects.filter(projet=courant.projet).in_most_recent_campagne()
    ) == [courant]


def test_a_non_courant_enveloppe_projet_on_a_later_campagne_does_not_close_it():
    projet = ProjetFactory()
    perimetre = projet.dossier_ds.perimetre
    notifie = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
        notified_at=timezone.now(),
        is_courant=False,
    )

    assert projet.enveloppe_projets_in_most_recent_campagne == [notifie]
    assert list(
        EnveloppeProjet.objects.filter(projet=projet).in_most_recent_campagne()
    ) == [notifie]


def test_enveloppe_projets_in_most_recent_campagne_reads_the_prefetch(
    django_assert_num_queries,
):
    enveloppe_projet = EnveloppeProjetFactory(
        status=ProjetStatus.ACCEPTED, notified_at=timezone.now()
    )
    projet = Projet.objects.get(pk=enveloppe_projet.projet_id)

    with django_assert_num_queries(0):
        assert projet.enveloppe_projets_in_most_recent_campagne == [enveloppe_projet]


def test_is_multi_campagnes():
    projet = ProjetFactory()
    perimetre = projet.dossier_ds.perimetre
    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
    )
    enveloppe_projets = EnveloppeProjet.objects.filter(projet=projet)
    assert enveloppe_projets.is_multi_campagnes() is False

    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
    )
    assert enveloppe_projets.is_multi_campagnes() is True

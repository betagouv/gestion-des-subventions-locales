from datetime import UTC, datetime

import pytest

from dn.sync.models import Dossier
from dn.sync.tests.factories import DossierFactory
from gsl.core.tests.factories import PerimetreDepartementalFactory
from gsl.programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory

from ....constants import ProjetStatus
from ....models import EnveloppeProjet
from ....services.enveloppe_projet_services import EnveloppeProjetService
from ...factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

synchroniser = EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet

DATE_TRAITEMENT = datetime(2026, 3, 15, tzinfo=UTC)
DATE_NOTIFICATION_PRECEDENTE = datetime(2026, 1, 10, tzinfo=UTC)


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


def _projet(perimetre, **dossier_kwargs):
    return ProjetFactory(
        dossier_ds=DossierFactory(
            perimetre=perimetre,
            demande_dispositif_sollicite="DETR",
            **dossier_kwargs,
        )
    )


def test_a_treated_dossier_notifies_its_programmed_enveloppe_projets(perimetre):
    projet = _projet(
        perimetre, ds_state=Dossier.State.REFUSE, ds_date_traitement=DATE_TRAITEMENT
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
    )

    synchroniser(projet)

    (enveloppe_projet,) = EnveloppeProjet.objects.filter(projet=projet)
    assert enveloppe_projet.notified_at == DATE_TRAITEMENT


def test_a_treated_dossier_keeps_an_existing_notification_date(perimetre):
    projet = _projet(
        perimetre, ds_state=Dossier.State.REFUSE, ds_date_traitement=DATE_TRAITEMENT
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )

    synchroniser(projet)

    (enveloppe_projet,) = EnveloppeProjet.objects.filter(projet=projet)
    assert enveloppe_projet.notified_at == DATE_NOTIFICATION_PRECEDENTE


def test_a_dossier_back_in_instruction_keeps_the_date_on_the_superseded_one(
    perimetre,
):
    projet = _projet(
        perimetre,
        ds_state=Dossier.State.EN_INSTRUCTION,
        ds_date_traitement=DATE_NOTIFICATION_PRECEDENTE,
        ds_date_passage_en_instruction=DATE_TRAITEMENT,
    )
    ancien = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        date_programmation=DATE_NOTIFICATION_PRECEDENTE,
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )

    synchroniser(projet)

    ancien.refresh_from_db()
    assert ancien.is_courant is False
    assert ancien.notified_at == DATE_NOTIFICATION_PRECEDENTE
    (courant,) = EnveloppeProjet.objects.filter(projet=projet)
    assert courant.status == ProjetStatus.PROCESSING
    assert courant.notified_at is None


def test_a_dossier_in_instruction_does_not_notify_the_one_programmed_in_turgot(
    perimetre,
):
    projet = _projet(perimetre, ds_state=Dossier.State.EN_INSTRUCTION)
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )
    # Programmed in Turgot, but not notified yet on DN.
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DsilEnveloppeFactory(perimetre=perimetre, annee=2027),
    )

    synchroniser(projet)

    closed.refresh_from_db()
    recent.refresh_from_db()
    assert closed.notified_at == DATE_NOTIFICATION_PRECEDENTE
    assert recent.status == ProjetStatus.REFUSED
    assert recent.notified_at is None


def test_a_retour_en_instruction_supersedes_the_most_recent_campagne_but_not_the_closed(
    perimetre,
):
    projet = _projet(
        perimetre,
        ds_state=Dossier.State.EN_INSTRUCTION,
        ds_date_traitement=DATE_NOTIFICATION_PRECEDENTE,
        ds_date_passage_en_instruction=DATE_TRAITEMENT,
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        # Programmed before the retour en instruction too: only its campagne
        # protects it.
        date_programmation=DATE_NOTIFICATION_PRECEDENTE,
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DsilEnveloppeFactory(perimetre=perimetre, annee=2027),
        # Programmed before the retour en instruction, so DN wins.
        date_programmation=DATE_NOTIFICATION_PRECEDENTE,
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )

    synchroniser(projet)

    closed.refresh_from_db()
    assert closed.is_courant is True
    assert closed.status == ProjetStatus.REFUSED
    assert closed.notified_at == DATE_NOTIFICATION_PRECEDENTE

    recent.refresh_from_db()
    assert recent.is_courant is False
    assert recent.status == ProjetStatus.REFUSED
    assert recent.notified_at == DATE_NOTIFICATION_PRECEDENTE
    assert (
        EnveloppeProjet.all_objects.filter(enveloppe__annee=2027, projet=projet).count()
        == 2
    )

    nouveau = EnveloppeProjet.objects.get(
        enveloppe__annee=2027, projet=projet, is_courant=True
    )
    assert nouveau.status == ProjetStatus.PROCESSING
    assert nouveau.notified_at is None


def test_a_retour_en_instruction_leaves_the_closed_one_of_the_same_dotation(
    perimetre,
):
    projet = _projet(
        perimetre,
        ds_state=Dossier.State.EN_INSTRUCTION,
        ds_date_traitement=DATE_NOTIFICATION_PRECEDENTE,
        ds_date_passage_en_instruction=DATE_TRAITEMENT,
    )
    # Created last, the closed one is the last read: it must not win the dotation.
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
        date_programmation=DATE_NOTIFICATION_PRECEDENTE,
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        date_programmation=DATE_NOTIFICATION_PRECEDENTE,
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )

    synchroniser(projet)

    closed.refresh_from_db()
    assert closed.is_courant is True
    assert closed.status == ProjetStatus.REFUSED
    assert closed.notified_at == DATE_NOTIFICATION_PRECEDENTE

    recent.refresh_from_db()
    assert recent.is_courant is False
    assert recent.notified_at == DATE_NOTIFICATION_PRECEDENTE
    nouveau = EnveloppeProjet.objects.get(enveloppe__annee=2027, projet=projet)
    assert nouveau.status == ProjetStatus.PROCESSING


def test_a_refused_dossier_leaves_the_closed_one_of_the_same_dotation(perimetre):
    # Treated during the 2027 campagne, so programmed on its enveloppe.
    date_traitement = datetime(2027, 3, 15, tzinfo=UTC)
    projet = _projet(
        perimetre, ds_state=Dossier.State.REFUSE, ds_date_traitement=date_traitement
    )
    # Created last, the closed one is the last read: it must not win the dotation.
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.ACCEPTED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        notified_at=DATE_NOTIFICATION_PRECEDENTE,
    )

    synchroniser(projet)

    closed.refresh_from_db()
    assert closed.status == ProjetStatus.ACCEPTED
    assert closed.notified_at == DATE_NOTIFICATION_PRECEDENTE

    recent.refresh_from_db()
    assert recent.status == ProjetStatus.REFUSED
    assert recent.notified_at == date_traitement


def test_the_dn_annotations_leave_the_closed_one_of_the_same_dotation(perimetre):
    projet = _projet(
        perimetre,
        ds_state=Dossier.State.EN_INSTRUCTION,
        annotations_assiette_detr=50_000,
        annotations_ej_detr="EJ-2027",
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2026),
        assiette=10_000,
        ej="EJ-2026",
    )
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=2027),
    )

    synchroniser(projet)

    closed.refresh_from_db()
    assert closed.assiette == 10_000
    assert closed.ej == "EJ-2026"

    recent.refresh_from_db()
    assert recent.assiette == 50_000
    assert recent.ej == "EJ-2027"

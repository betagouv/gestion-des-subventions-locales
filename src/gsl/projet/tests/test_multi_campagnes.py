"""A projet with enveloppe projets on several campagnes: only the most recent one
goes on, the older ones are closed."""

from datetime import UTC, datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from django_fsm import TransitionNotAllowed

from dn.sync.models import Dossier
from dn.sync.tests.factories import DossierFactory
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl.programmation.tests.factories import DetrEnveloppeFactory
from gsl.simulation.models import SimulationProjet
from gsl.simulation.tests.factories import SimulationFactory

from ..constants import ProjetStatus
from ..models import EnveloppeProjet
from ..services.enveloppe_projet_services import EnveloppeProjetService
from .factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

CAMPAGNE = 2026


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


def _projet_sur_deux_campagnes(perimetre, **dossier_kwargs):
    """DETR refused and notified on CAMPAGNE, in processing on the next one."""
    projet = ProjetFactory(
        dossier_ds=DossierFactory(
            perimetre=perimetre, demande_dispositif_sollicite="DETR", **dossier_kwargs
        )
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE),
        notified_at=timezone.now(),
    )
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.PROCESSING,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE + 1),
    )
    return projet, closed, recent


def test_an_enveloppe_projet_of_an_older_campagne_cannot_be_set_back_to_processing(
    perimetre,
):
    _projet, closed, _recent = _projet_sur_deux_campagnes(perimetre)

    assert closed.is_closed is True
    with pytest.raises(TransitionNotAllowed):
        closed.set_back_status_to_processing_without_ds()


def test_the_simulation_of_the_most_recent_campagne_shows_its_enveloppe_projet(
    perimetre,
):
    _projet, _closed, recent = _projet_sur_deux_campagnes(perimetre)
    simulation = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE + 1)
    )
    SimulationProjet.objects.reset_for_enveloppe_projet(recent)
    client = ClientWithLoggedUserFactory(
        CollegueWithDSProfileFactory(perimetre=perimetre)
    )

    response = client.get(
        reverse("gsl_simulation:simulation-detail", kwargs={"slug": simulation.slug})
    )

    assert response.status_code == 200
    (row,) = response.context["page_obj"].object_list
    (enveloppe_projet,) = row.enveloppe_projet
    assert enveloppe_projet == recent
    assert len(enveloppe_projet.simu) == 1


def test_a_retour_en_instruction_only_reopens_the_most_recent_campagne(perimetre):
    notification_n = datetime(CAMPAGNE, 3, 1, tzinfo=UTC)
    notification_n_plus_1 = datetime(CAMPAGNE + 1, 3, 1, tzinfo=UTC)
    projet = ProjetFactory(
        dossier_ds=DossierFactory(
            perimetre=perimetre,
            demande_dispositif_sollicite="DETR",
            ds_state=Dossier.State.EN_INSTRUCTION,
            ds_date_traitement=notification_n_plus_1,
            ds_date_passage_en_instruction=datetime(CAMPAGNE + 1, 4, 1, tzinfo=UTC),
        )
    )
    closed = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE),
        date_programmation=notification_n,
        notified_at=notification_n,
    )
    recent = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.REFUSED,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE + 1),
        date_programmation=notification_n_plus_1,
        notified_at=notification_n_plus_1,
    )

    EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet(projet)

    closed.refresh_from_db()
    recent.refresh_from_db()
    assert (closed.is_courant, closed.status, closed.notified_at) == (
        True,
        ProjetStatus.REFUSED,
        notification_n,
    )
    assert recent.is_courant is False
    (courant,) = EnveloppeProjet.objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE + 1
    )
    assert courant.status == ProjetStatus.PROCESSING

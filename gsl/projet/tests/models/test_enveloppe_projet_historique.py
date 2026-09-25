import pytest
from django.db import IntegrityError, transaction

from gsl.simulation.tests.factories import SimulationProjetFactory

from ...constants import DOTATION_DETR, ProjetStatus
from ...models import EnveloppeProjet
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def projet():
    return ProjetFactory()


@pytest.fixture
def non_courant(projet):
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )
    EnveloppeProjet.objects.filter(pk=enveloppe_projet.pk).update(is_courant=False)
    enveloppe_projet.refresh_from_db()
    return enveloppe_projet


def test_objects_exclut_les_non_courants(non_courant):
    assert EnveloppeProjet.objects.filter(pk=non_courant.pk).count() == 0


def test_all_objects_inclut_les_non_courants(non_courant):
    assert EnveloppeProjet.all_objects.filter(pk=non_courant.pk).count() == 1


def test_acces_inverse_depuis_projet_exclut_les_non_courants(projet, non_courant):
    assert projet.enveloppeprojet_set.count() == 0


def test_acces_par_cle_etrangere_atteint_un_non_courant(non_courant):
    simulation_projet = SimulationProjetFactory(enveloppe_projet=non_courant)

    simulation_projet.refresh_from_db()

    assert simulation_projet.enveloppe_projet == non_courant


def test_deux_courants_de_meme_dotation_sont_refuses(projet):
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        EnveloppeProjet.objects.create(
            projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
        )


def test_un_non_courant_ne_bloque_pas_un_nouveau_courant(projet, non_courant):
    nouveau = EnveloppeProjet.objects.create(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.PROCESSING
    )

    assert list(projet.enveloppeprojet_set.all()) == [nouveau]
    assert projet.enveloppeprojet_set.count() == 1
    assert EnveloppeProjet.all_objects.filter(projet=projet).count() == 2

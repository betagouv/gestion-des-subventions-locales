from importlib import import_module

import pytest
from django.apps import apps
from django.utils import timezone

from ..constants import ProjetStatus
from ..models import EnveloppeProjet
from .factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

migration = import_module(
    "gsl.projet.migrations.0045_initialize_enveloppeprojet_notified_at"
)


def test_programmed_enveloppe_projets_of_a_notified_projet_get_its_date():
    notified_at = timezone.now()
    notified = ProjetFactory(notified_at=notified_at)
    programmed = EnveloppeProjetFactory(projet=notified, status=ProjetStatus.REFUSED)
    processing = EnveloppeProjetFactory(
        status=ProjetStatus.PROCESSING, projet__notified_at=notified_at
    )
    not_notified = EnveloppeProjetFactory(status=ProjetStatus.ACCEPTED)
    historique = EnveloppeProjetFactory(
        projet=ProjetFactory(notified_at=notified_at),
        status=ProjetStatus.REFUSED,
        is_courant=False,
    )

    migration.initialize_notified_at(apps, None)

    def notified_at_of(enveloppe_projet):
        return EnveloppeProjet.all_objects.get(pk=enveloppe_projet.pk).notified_at

    assert notified_at_of(programmed) == notified_at
    assert notified_at_of(processing) is None
    assert notified_at_of(not_notified) is None
    assert notified_at_of(historique) is None

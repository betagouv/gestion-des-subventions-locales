import pytest

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.tests.factories import PersonneMoraleFactory

from ..models import (
    Demandeur,
    Dotation,
    Projet,
)
from .factories import (
    DemandeurFactory,
    DotationFactory,
    ProcessedProjetFactory,
    ProjetFactory,
    SubmittedProjetFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (DotationFactory, Dotation),
    (DemandeurFactory, Demandeur),
    (ProjetFactory, Projet),
    (SubmittedProjetFactory, Projet),
    (ProcessedProjetFactory, Projet),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(3):
        obj = factory()
        assert isinstance(obj, expected_class)


def test_projet_factory_can_be_called_twice_with_same_demandeur():
    demandeur = PersonneMoraleFactory()
    ProjetFactory.create_batch(2, dossier_ds__ds_demandeur=demandeur)
    assert Projet.objects.count() == 2
    assert Perimetre.objects.count() == 1

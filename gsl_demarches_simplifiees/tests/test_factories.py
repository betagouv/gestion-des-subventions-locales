import pytest

from gsl_demarches_simplifiees.models import (
    Arrondissement,
    Demarche,
    Dossier,
    NaturePorteurProjet,
    PersonneMorale,
)

from .factories import (
    DemarcheFactory,
    DossierFactory,
    DsArrondissementFactory,
    NaturePorteurProjetFactory,
    PersonneMoraleFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (DemarcheFactory, Demarche),
    (DossierFactory, Dossier),
    (NaturePorteurProjetFactory, NaturePorteurProjet),
    (DsArrondissementFactory, Arrondissement),
    (PersonneMoraleFactory, PersonneMorale),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)

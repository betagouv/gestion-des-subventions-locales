import pytest

from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    Demarche,
    Departement,
    Dossier,
    FieldMapping,
    NaturePorteurProjet,
    PersonneMorale,
    Profile,
)

from .factories import (
    CategorieDetrFactory,
    DemarcheFactory,
    DossierFactory,
    DsDepartementFactory,
    FieldMappingFactory,
    NaturePorteurProjetFactory,
    PersonneMoraleFactory,
    ProfileFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (DemarcheFactory, Demarche),
    (DossierFactory, Dossier),
    (NaturePorteurProjetFactory, NaturePorteurProjet),
    (DsDepartementFactory, Departement),
    (PersonneMoraleFactory, PersonneMorale),
    (FieldMappingFactory, FieldMapping),
    (ProfileFactory, Profile),
    (CategorieDetrFactory, CategorieDetr),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)

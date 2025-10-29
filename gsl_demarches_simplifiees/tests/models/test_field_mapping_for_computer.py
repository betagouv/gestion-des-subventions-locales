import pytest

from gsl_demarches_simplifiees.tests.factories import (
    FieldMappingForComputerFactory,
)


@pytest.mark.django_db
def test_django_field_label_with_empty_django_field():
    mapping = FieldMappingForComputerFactory(django_field="")

    assert mapping.django_field_type == ""
    assert mapping.django_field_label == ""


@pytest.mark.django_db
def test_django_field_label_with_existing_django_field():
    mapping = FieldMappingForComputerFactory(django_field="finance_cout_total")

    assert mapping.django_field_type == "DecimalField"
    assert mapping.django_field_label == "Coût total de l'opération (en euros HT)"

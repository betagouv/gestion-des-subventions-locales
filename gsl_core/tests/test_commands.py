import logging

import pytest
from django.core.management import call_command

from gsl_core.models import Arrondissement, Departement, Perimetre, Region
from gsl_core.tests.factories import (
    ArrondissementFactory,
    PerimetreArrondissementFactory,
)


@pytest.mark.django_db
def test_create_perimetres(caplog):
    arrondissements = ArrondissementFactory.create_batch(10)
    PerimetreArrondissementFactory(arrondissement=arrondissements[0])
    assert Perimetre.objects.count() == 1
    assert Arrondissement.objects.count() == 10
    assert Departement.objects.count() == 10
    assert Region.objects.count() == 10

    with caplog.at_level(logging.INFO):
        call_command("create_perimetres")

    perimetres = Perimetre.objects
    assert perimetres.filter(arrondissement__isnull=True).count() == 20
    assert perimetres.filter(departement__isnull=True).count() == 10
    assert perimetres.count() == 30

    assert "Et voilà le travail, 29 périmètres ont été créés" in caplog.text

import logging

import pytest
import responses
from django.core.management import call_command

from gsl_core.management.commands.import_cog import COG_BASE_URL, COG_MILLESIME
from gsl_core.models import Arrondissement, Commune, Departement, Perimetre, Region
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


def mock_cog_csv(filename, content):
    responses.get(
        f"{COG_BASE_URL}/{filename}",
        body=content.strip(),
        content_type="text/csv",
    )


def mock_cog_files():
    mock_cog_csv(
        f"v_region_{COG_MILLESIME}.csv",
        """
"REG","CHEFLIEU","TNCC","NCC","NCCENR","LIBELLE"
"84","69123","1","AUVERGNE RHONE ALPES","Auvergne-Rhône-Alpes","Auvergne-Rhône-Alpes"
""",
    )
    mock_cog_csv(
        f"v_departement_{COG_MILLESIME}.csv",
        """
"DEP","REG","CHEFLIEU","TNCC","NCC","NCCENR","LIBELLE"
"01","84","01053","5","AIN","Ain","Ain"
""",
    )
    mock_cog_csv(
        f"v_arrondissement_{COG_MILLESIME}.csv",
        """
"ARR","DEP","REG","CHEFLIEU","TNCC","NCC","NCCENR","LIBELLE"
"011","01","84","01034","0","BELLEY","Belley","Belley"
""",
    )
    mock_cog_csv(
        f"v_commune_{COG_MILLESIME}.csv",
        """
"TYPECOM","COM","REG","DEP","CTCD","ARR","TNCC","NCC","NCCENR","LIBELLE","CAN","COMPARENT"
"COM","01004","84","01","01D","011","1","AMBERIEU EN BUGEY","Ambérieu-en-Bugey","Ambérieu-en-Bugey","0101",""
"COMD","01015","","","","","1","ARBIGNIEU","Arbignieu","Arbignieu","","01015"
""",
    )


@pytest.mark.django_db
@responses.activate
def test_import_cog():
    mock_cog_files()

    call_command("import_cog")

    region = Region.objects.get()
    assert region.insee_code == "84"
    assert region.name == "Auvergne-Rhône-Alpes"

    departement = Departement.objects.get()
    assert departement.insee_code == "01"
    assert departement.name == "Ain"
    assert departement.region == region

    arrondissement = Arrondissement.objects.get()
    assert arrondissement.insee_code == "011"
    assert arrondissement.name == "Belley"
    assert arrondissement.departement == departement

    # The commune déléguée (COMD) is skipped.
    commune = Commune.objects.get()
    assert commune.insee_code == "01004"
    assert commune.name == "Ambérieu-en-Bugey"
    assert commune.departement == departement
    assert commune.arrondissement == arrondissement


@pytest.mark.django_db
@responses.activate
def test_import_cog_is_idempotent():
    mock_cog_files()
    call_command("import_cog")

    mock_cog_files()
    Commune.objects.update(name="Ancien nom")
    call_command("import_cog")

    assert Commune.objects.count() == 1
    assert Commune.objects.get().name == "Ambérieu-en-Bugey"

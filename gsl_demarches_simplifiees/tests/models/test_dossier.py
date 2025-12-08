import logging

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    DsArrondissementFactory,
    DsDepartementFactory,
)

pytestmark = pytest.mark.django_db


def test_get_projet_perimetre_nominal_case_get_arrondissement_if_available():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    declared_arrondissement = DsArrondissementFactory(
        core_arrondissement=perimetre_arrondissement.arrondissement
    )
    perimetre_departement = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement.departement
    )
    declared_departement = DsDepartementFactory(
        core_departement=perimetre_departement.departement
    )
    dossier = DossierFactory(
        porteur_de_projet_arrondissement=declared_arrondissement,
        porteur_de_projet_departement=declared_departement,
    )

    assert dossier.get_projet_perimetre() == perimetre_arrondissement


def test_get_perimetre_for_departement_without_arrondissement(caplog):
    perimetre_departement = PerimetreDepartementalFactory()
    declared_departement = DsDepartementFactory(
        core_departement=perimetre_departement.departement
    )
    assert not declared_departement.core_departement.arrondissement_set.exists()

    dossier = DossierFactory(
        porteur_de_projet_arrondissement=None,
        porteur_de_projet_departement=declared_departement,
    )

    with caplog.at_level(logging.WARNING):
        assert dossier.get_projet_perimetre() == perimetre_departement
    assert len(caplog.records) == 0, "No warning should be raised in this case."


def test_get_perimetre_yields_warning_if_arrondissement_is_missing_when_expected(
    caplog,
):
    perimetre_arrondissement = PerimetreArrondissementFactory()
    perimetre_departement = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement.departement
    )
    declared_departement = DsDepartementFactory(
        core_departement=perimetre_departement.departement
    )
    assert declared_departement.core_departement.arrondissement_set.exists()

    dossier = DossierFactory(
        porteur_de_projet_arrondissement=None,
        porteur_de_projet_departement=declared_departement,
    )

    with caplog.at_level(logging.WARNING):
        assert dossier.get_projet_perimetre() == perimetre_departement
    assert len(caplog.records) == 1, "A warning should be raised in this case."


@pytest.mark.parametrize(
    "demande_montant, finance_cout_total, expected_taux",
    (
        (None, None, None),
        (None, 1_000, None),
        (1_000, None, None),
        (1_000, 10_000, 10),
        (1_000, 3_000, 33.33),
        (2_000, 3_000, 66.67),
    ),
)
def test_taux_demande(demande_montant, finance_cout_total, expected_taux):
    dossier = DossierFactory(
        demande_montant=demande_montant,
        finance_cout_total=finance_cout_total,
    )
    assert dossier.taux_demande == expected_taux

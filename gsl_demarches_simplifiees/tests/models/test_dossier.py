import pytest

from gsl_core.tests.factories import (
    AdresseFactory,
    CommuneFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    DsArrondissementFactory,
    PersonneMoraleFactory,
)

pytestmark = pytest.mark.django_db


def test_get_declared_arrondissement_even_with_demandeur_arrondissement():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    declared_arrondissement = DsArrondissementFactory(
        core_arrondissement=perimetre_arrondissement.arrondissement
    )

    demandeur = PersonneMoraleFactory()
    demandeur_arrondissement = demandeur.address.commune.arrondissement
    assert perimetre_arrondissement.arrondissement != demandeur_arrondissement
    dossier = DossierFactory(
        ds_demandeur=demandeur,
        porteur_de_projet_arrondissement=declared_arrondissement,
    )

    perimetre = dossier.perimetre

    assert perimetre == perimetre_arrondissement
    assert perimetre.arrondissement != demandeur_arrondissement


def test_get_declared_arrondissement_if_no_arrondissement_provided_on_demandeur():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    demandeur_without_arrondissement = PersonneMoraleFactory(
        address=AdresseFactory(
            commune=CommuneFactory(
                arrondissement=None, departement=perimetre_arrondissement.departement
            )
        )
    )
    declared_arrondissement = DsArrondissementFactory(
        core_arrondissement=perimetre_arrondissement.arrondissement
    )
    dossier = DossierFactory(
        ds_demandeur=demandeur_without_arrondissement,
        porteur_de_projet_arrondissement=declared_arrondissement,
    )

    perimetre = dossier.perimetre

    assert perimetre == perimetre_arrondissement
    assert perimetre.arrondissement == declared_arrondissement.core_arrondissement


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

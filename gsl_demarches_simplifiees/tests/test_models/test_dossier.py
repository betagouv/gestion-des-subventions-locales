import pytest

from gsl_core.tests.factories import (
    AdresseFactory,
    CommuneFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    DsArrondissementFactory,
    PersonneMoraleFactory,
)

pytestmark = pytest.mark.django_db


def test_get_demandeur_departement_if_nothing_better():
    perimetre_departement = PerimetreDepartementalFactory()
    demandeur_without_arrondissement = PersonneMoraleFactory(
        address=AdresseFactory(
            commune=CommuneFactory(
                arrondissement=None, departement=perimetre_departement.departement
            )
        )
    )
    dossier = DossierFactory(
        ds_demandeur=demandeur_without_arrondissement,
        porteur_de_projet_arrondissement=None,
    )

    perimetre = dossier.perimetre

    assert perimetre == perimetre_departement


def test_get_demandeur_arrondissement_event_with_declared_arrondissement():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    demandeur_with_arrondissement = PersonneMoraleFactory(
        address=AdresseFactory(
            commune=CommuneFactory(
                arrondissement=perimetre_arrondissement.arrondissement,
                departement=perimetre_arrondissement.departement,
            )
        )
    )
    declared_arrondissement = DsArrondissementFactory()
    assert (
        perimetre_arrondissement.arrondissement
        != declared_arrondissement.core_arrondissement
    )
    dossier = DossierFactory(
        ds_demandeur=demandeur_with_arrondissement,
        porteur_de_projet_arrondissement=declared_arrondissement,
    )

    perimetre = dossier.perimetre

    assert perimetre == perimetre_arrondissement
    assert perimetre.arrondissement != declared_arrondissement.core_arrondissement


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

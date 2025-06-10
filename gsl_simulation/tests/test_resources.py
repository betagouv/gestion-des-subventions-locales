from datetime import date, datetime

import pytest

from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_projet.tests.factories import (
    DemandeurFactory,
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.resources import (
    DetrSimulationProjetResource,
    DsilSimulationProjetResource,
)
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


def test_dsil_meta_fields():
    assert DsilSimulationProjetResource.Meta.fields == (
        "date_depot",
        "dossier_number",
        "projet_intitule",
        "demandeur_name",
        "porteur_name",
        "demandeur_code_insee",
        "arrondissement",
        "has_double_dotations",
        "cout_total",
        "assiette",
        "demande_montant",
        "demande_taux",
        "montant",
        "taux",
        "status",
        "date_debut",
        "date_achevement",
        "is_in_qpv",
        "is_attached_to_a_crte",
        "is_budget_vert",
        "demande_priorite_dsil_detr",
        "priorite",
        "annotations",
    )


def test_detr_meta_fields():
    assert DetrSimulationProjetResource.Meta.fields == (
        "date_depot",
        "dossier_number",
        "projet_intitule",
        "demandeur_name",
        "porteur_name",
        "demandeur_code_insee",
        "arrondissement",
        "has_double_dotations",
        "cout_total",
        "assiette",
        "demande_montant",
        "demande_taux",
        "montant",
        "taux",
        "status",
        "date_debut",
        "date_achevement",
        "is_in_qpv",
        "is_attached_to_a_crte",
        "is_budget_vert",
        "demande_priorite_dsil_detr",
        "priorite",
        "annotations",
        "can_have_a_commission_detr_avis",
        "detr_avis_commission",
    )


@pytest.fixture
def projet():
    dossier_ds = DossierFactory(
        ds_date_depot=datetime(2024, 12, 1),
        ds_number=12345678,
        projet_intitule="Intitulé",
        porteur_de_projet_nom="Jean-Marc",
        porteur_de_projet_prenom="Jancovici",
        finance_cout_total=120_000,
        demande_montant=30_000,
        date_debut=date(2025, 1, 1),
        date_achevement=date(2025, 5, 1),
        demande_priorite_dsil_detr=2,
        annotations_champ_libre="Ceci est une annotation",
    )
    demandeur = DemandeurFactory(
        name="Commune de Baume-les-Messieurs",
        address__commune__insee_code=39210,
        address__commune__arrondissement__name="Lons-le-Saunier",
    )
    return ProjetFactory(
        dossier_ds=dossier_ds,
        demandeur=demandeur,
        is_in_qpv=True,
        is_attached_to_a_crte=False,
        is_budget_vert=None,
    )


@pytest.fixture
def detr_simulation():
    return SimulationFactory(enveloppe=DetrEnveloppeFactory())


@pytest.fixture
def detr_simulation_projet(projet, detr_simulation):
    detr_projet = DetrProjetFactory(
        projet=projet,
        assiette=100_000,
        detr_avis_commission=True,
    )

    return SimulationProjetFactory(
        simulation=detr_simulation,
        dotation_projet=detr_projet,
        montant=25_000,
        status=SimulationProjet.STATUS_PROCESSING,
    )


@pytest.mark.django_db
def test_detr_simulation_projet(detr_simulation_projet):
    qs = SimulationProjet.objects.all()
    resource = DetrSimulationProjetResource()
    dataset = resource.export(qs)
    export_data = dataset.csv
    splited_data = export_data.split("\n")
    assert (
        splited_data[0]
        == "Date de dépôt du dossier,Numéro de dossier DS,Intitulé du projet,Demandeur,Nom et prénom du demandeur,Code INSEE commune du demandeur,Code INSEE commune du demandeur,Projet en double dotation,Coût total du projet,Assiette subventionnable,Montant demandé,Taux demandé par rapport au coût total,Montant prévsionnel accordé,Taux prévsionnel accordé,Statut de la simulation,Date de début des travaux,Date de fin des travaux,Projet situé dans un QPV,Projet rattaché à un CRTE,Projet concourant à la transition écologique,Priorité du projet,Annotation de l’instructeur,Montant demandé supérieur à 100 000€ ?,Avis de la commission\r"
    )
    assert (
        splited_data[1]
        == "01/12/2024,12345678,Intitulé,Commune de Baume-les-Messieurs,Jean-Marc Jancovici,39210,Lons-le-Saunier,Non,120000.00,100000.00,30000.00,25.00,25000.00,25.000,🔄 En traitement,01/01/2025,01/05/2025,Oui,Non,Inconnu,2,Ceci est une annotation,Non,Oui\r"
    )


@pytest.fixture
def dsil_simulation():
    return SimulationFactory(enveloppe=DsilEnveloppeFactory())


@pytest.fixture
def dsil_simulation_projet(projet, dsil_simulation):
    detr_projet = DsilProjetFactory(
        projet=projet,
        assiette=90_000,
    )

    return SimulationProjetFactory(
        simulation=dsil_simulation,
        dotation_projet=detr_projet,
        montant=30_000,
        status=SimulationProjet.STATUS_ACCEPTED,
    )


@pytest.mark.django_db
def test_dsil_simulation_projet(dsil_simulation_projet):
    qs = SimulationProjet.objects.all()
    resource = DsilSimulationProjetResource()
    dataset = resource.export(qs)
    export_data = dataset.csv
    splited_data = export_data.split("\n")
    assert (
        splited_data[0]
        == "Date de dépôt du dossier,Numéro de dossier DS,Intitulé du projet,Demandeur,Nom et prénom du demandeur,Code INSEE commune du demandeur,Code INSEE commune du demandeur,Projet en double dotation,Coût total du projet,Assiette subventionnable,Montant demandé,Taux demandé par rapport au coût total,Montant prévsionnel accordé,Taux prévsionnel accordé,Statut de la simulation,Date de début des travaux,Date de fin des travaux,Projet situé dans un QPV,Projet rattaché à un CRTE,Projet concourant à la transition écologique,Priorité du projet,Annotation de l’instructeur\r"
    )
    assert (
        splited_data[1]
        == "01/12/2024,12345678,Intitulé,Commune de Baume-les-Messieurs,Jean-Marc Jancovici,39210,Lons-le-Saunier,Non,120000.00,90000.00,30000.00,25.00,30000.00,33.333,✅ Accepté,01/01/2025,01/05/2025,Oui,Non,Inconnu,2,Ceci est une annotation\r"
    )

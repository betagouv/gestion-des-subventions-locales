from datetime import UTC
from decimal import Decimal

import pytest
from django.utils import timezone

from gsl_core.tests.factories import AdresseFactory, PerimetreArrondissementFactory
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import Simulation
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.mark.django_db
def test_get_or_create_projet_from_dossier_with_existing_projet():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = ProjetFactory(dossier_ds=dossier)

    assert ProjetService.get_or_create_from_ds_dossier(dossier) == projet


@pytest.mark.django_db
def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    demandeur_commune = dossier.ds_demandeur.address.commune
    perimetre = PerimetreArrondissementFactory(
        arrondissement=demandeur_commune.arrondissement,
    )
    assert (
        dossier.ds_demandeur.address.commune.arrondissement == perimetre.arrondissement
    )
    assert dossier.ds_demandeur.address.commune.departement == perimetre.departement

    projet = ProjetService.get_or_create_from_ds_dossier(dossier)

    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse
    assert projet.perimetre == perimetre

    other_projet = ProjetService.get_or_create_from_ds_dossier(dossier)
    assert other_projet == projet


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def projets_with_assiette(simulation):
    for amount in (10_000, 20_000, 30_000):
        p = ProjetFactory(assiette=amount)
        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.fixture
def projets_without_assiette_but_finance_cout_total_from_dossier_ds(
    simulation,
):
    for amount in (15_000, 25_000):
        p = ProjetFactory(
            dossier_ds__finance_cout_total=amount,
            assiette=None,
        )

        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.fixture
def projets_with_assiette_but_not_in_simulation():
    p = ProjetFactory(assiette=50_000)
    SimulationProjetFactory(projet=p)


@pytest.mark.django_db
def test_get_total_cost_with_assiette(simulation, projets_with_assiette):
    qs = Projet.objects.all()
    assert ProjetService.get_total_cost(qs) == 60_000


@pytest.mark.django_db
def test_get_total_cost_without_assiette(
    simulation, projets_without_assiette_but_finance_cout_total_from_dossier_ds
):
    qs = Projet.objects.all()

    assert ProjetService.get_total_cost(qs) == 40_000


@pytest.mark.django_db
def test_get_total_cost(
    simulation,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    qs = Projet.objects.all()
    assert ProjetService.get_total_cost(qs) == 100_000


@pytest.mark.django_db
def test_get_same_total_cost_even_if_there_is_other_projets(
    simulation,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
    projets_with_assiette_but_not_in_simulation,
):
    qs = Projet.objects.filter(simulationprojet__simulation=simulation).all()
    assert ProjetService.get_total_cost(qs) == 100_000


@pytest.mark.django_db
def test_get_total_amount_granted(simulation):
    SimulationProjetFactory(simulation=simulation, montant=1000)
    SimulationProjetFactory(simulation=simulation, montant=2000)
    SimulationProjetFactory(montant=4000)

    qs = Projet.objects.filter(simulationprojet__simulation=simulation).all()
    assert ProjetService.get_total_amount_granted(qs) == 3000


@pytest.fixture
def projets_with_dossier_ds__demande_montant_not_in_simulation() -> None:
    for amount in (10_000, 2_000):
        p = ProjetFactory(
            dossier_ds__demande_montant=amount,
        )
        SimulationProjetFactory(projet=p)


@pytest.fixture
def projets_with_dossier_ds__demande_montant_in_simulation(
    simulation,
) -> None:
    for amount in (15_000, 25_000):
        p = ProjetFactory(
            dossier_ds__demande_montant=amount,
        )

        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.mark.django_db
def test_get_total_amount_asked(
    simulation,
    projets_with_dossier_ds__demande_montant_in_simulation,
    projets_with_dossier_ds__demande_montant_not_in_simulation,
):
    qs = Projet.objects.filter(simulationprojet__simulation=simulation).all()
    assert ProjetService.get_total_amount_asked(qs) == 15_000 + 25_000


@pytest.fixture
def create_projets():
    epci_nature = NaturePorteurProjetFactory(label="EPCI")
    commune_nature = NaturePorteurProjetFactory(label="Communes")
    for i in (49, 50, 100, 150, 151):
        ProjetFactory(
            assiette=i,
            dossier_ds=DossierFactory(
                demande_dispositif_sollicite="DETR",
                porteur_de_projet_nature=epci_nature,
            ),
        )
        ProjetFactory(
            assiette=i,
            dossier_ds=DossierFactory(
                demande_dispositif_sollicite="DETR",
                porteur_de_projet_nature=commune_nature,
            ),
        )
        ProjetFactory(
            assiette=i, dossier_ds=DossierFactory(demande_dispositif_sollicite="DSIL")
        )


@pytest.mark.django_db
def test_add_ordering_to_projets_qs():
    projet1 = ProjetFactory(
        dossier_ds__finance_cout_total=100,
        dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 1, tzinfo=UTC),
        address__commune__name="Beaune",
    )
    projet2 = ProjetFactory(
        dossier_ds__finance_cout_total=200,
        dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 2, tzinfo=UTC),
        address__commune__name="Dijon",
    )
    projet3 = ProjetFactory(
        dossier_ds__finance_cout_total=150,
        dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 3, tzinfo=UTC),
        address__commune__name="Auxonne",
    )

    ordering = "date_desc"
    qs = Projet.objects.all()
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet3, projet2, projet1]

    ordering = "date_asc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet1, projet2, projet3]

    ordering = "cout_desc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet2, projet3, projet1]

    ordering = "cout_asc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet1, projet3, projet2]

    ordering = "commune_desc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)
    assert list(ordered_qs) == [projet2, projet1, projet3]

    ordering = "commune_asc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)
    assert list(ordered_qs) == [projet3, projet1, projet2]


@pytest.mark.django_db
def test_compute_taux_from_montant():
    projet = ProjetFactory(
        dossier_ds__finance_cout_total=100_000,
    )
    taux = ProjetService.compute_taux_from_montant(projet, 10_000)
    assert taux == 10


@pytest.mark.django_db
def test_compute_taux_from_montant_with_projet_without_finance_cout_total():
    projet = ProjetFactory()
    taux = ProjetService.compute_taux_from_montant(projet, 10_000)
    assert taux == 0


@pytest.mark.parametrize(
    "montant, assiette, expected_taux",
    (
        (10_000, 30_000, 33.33),
        (10_000, 0, 0),
        (10_000, 10_000, 100),
        (100_000, 10_000, 100),
        (10_000, -3_000, 0),
        (0, 0, 0),
        (1_000, None, 0),
        (None, 4_000, 0),
    ),
)
@pytest.mark.django_db
def test_compute_taux_from_montant_with_projet_without_assiette(
    assiette, montant, expected_taux
):
    projet = ProjetFactory(assiette=assiette)
    taux = ProjetService.compute_taux_from_montant(projet, montant)
    assert taux == round(Decimal(expected_taux), 2)


def test_get_projet_status():
    accepted = Dossier(ds_state=Dossier.STATE_ACCEPTE)
    en_construction = Dossier(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    en_instruction = Dossier(ds_state=Dossier.STATE_EN_INSTRUCTION)
    refused = Dossier(ds_state=Dossier.STATE_REFUSE)
    unanswered = Dossier(ds_state=Dossier.STATE_SANS_SUITE)

    assert ProjetService.get_projet_status(accepted) == Projet.STATUS_ACCEPTED
    assert ProjetService.get_projet_status(en_construction) == Projet.STATUS_PROCESSING
    assert ProjetService.get_projet_status(en_instruction) == Projet.STATUS_PROCESSING
    assert ProjetService.get_projet_status(refused) == Projet.STATUS_REFUSED
    assert ProjetService.get_projet_status(unanswered) == Projet.STATUS_UNANSWERED

    dossier_unknown = Dossier(ds_state="unknown_state")
    assert ProjetService.get_projet_status(dossier_unknown) is None


@pytest.mark.parametrize(
    "taux, should_raise_exception",
    [
        (50, False),
        (0, False),
        (100, False),
        (-1, True),
        (101, True),
        (None, True),
        ("invalid", True),
    ],
)
def test_validate_taux(taux, should_raise_exception):
    if should_raise_exception:
        with pytest.raises(ValueError, match=f"Taux {taux} must be between 0 and 100"):
            ProjetService.validate_taux(taux)
    else:
        ProjetService.validate_taux(taux)

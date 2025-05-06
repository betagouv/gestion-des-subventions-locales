from datetime import date
from decimal import Decimal

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "dotation_value, dotation_projet_count",
    (
        ("DETR", 1),
        ("['DETR']", 1),
        ("DSIL", 1),
        ("['DSIL']", 1),
        ("[DETR, DSIL]", 2),
        ("DETR et DSIL", 2),
        ("['DETR', 'DSIL', 'DETR et DSIL']", 2),
    ),
)
def test_create_or_update_dotation_projet_from_projet(
    field, dotation_value, dotation_projet_count
):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_assiette=1_000,
    )
    setattr(projet.dossier_ds, field, dotation_value)

    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    assert DotationProjet.objects.count() == dotation_projet_count

    for dotation_projet in DotationProjet.objects.all():
        assert dotation_projet.projet == projet
        assert dotation_projet.status == PROJET_STATUS_ACCEPTED
        assert dotation_projet.assiette == 1_000
        if dotation_projet.dotation == DOTATION_DSIL:
            assert dotation_projet.detr_avis_commission is None
        else:
            assert dotation_projet.detr_avis_commission is True


@pytest.mark.django_db
def test_create_or_update_dotation_projet_from_projet_do_not_remove_dotation_projet_not_in_dossier():
    projet = ProjetFactory(dossier_ds__annotations_dotation="DETR")
    projet_dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    projet_dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert projet_dotation_projets.count() == 1

    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    projet_dotation_dsil.refresh_from_db()  # always exists

    projet_dotation_projets = DotationProjet.objects.filter(projet_id=projet.id)
    assert projet_dotation_projets.count() == 2

    dotation_projet = projet_dotation_projets[0]
    assert dotation_projet.dotation == DOTATION_DSIL

    dotation_projet = projet_dotation_projets[1]
    assert dotation_projet.dotation == DOTATION_DETR


@pytest.mark.django_db
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DETR, DOTATION_DSIL),
)
def test_create_or_update_dotation_projet(dotation):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__annotations_assiette=2_000,
    )

    DotationProjetService.create_or_update_dotation_projet(projet, dotation)

    assert DotationProjet.objects.count() == 1

    dotation_projet = DotationProjet.objects.first()
    assert dotation_projet.projet == projet
    assert dotation_projet.dotation == dotation
    assert dotation_projet.status == PROJET_STATUS_DISMISSED
    assert dotation_projet.assiette == 2_000
    assert dotation_projet.detr_avis_commission is None


@pytest.fixture
def perimetres():
    arr_dijon = PerimetreArrondissementFactory()
    dep_21 = PerimetreDepartementalFactory(departement=arr_dijon.departement)
    region_bfc = PerimetreRegionalFactory(region=dep_21.region)

    arr_nanterre = PerimetreArrondissementFactory()
    dep_92 = PerimetreDepartementalFactory(departement=arr_nanterre.departement)
    region_idf = PerimetreRegionalFactory(region=dep_92.region)
    return [
        arr_dijon,
        dep_21,
        region_bfc,
        arr_nanterre,
        dep_92,
        region_idf,
    ]


@pytest.fixture
def simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation(
    perimetres,
):
    arr_nanterre, dep_92, region_idf, arr_dijon, dep_21, region_bfc = perimetres
    for annee in [date.today().year - 1, date.today().year, date.today().year + 1]:
        """
        Pour ces 3 années, on crée ces simulations :
        |--------------+-------+-------|
        | perimetre    | DETR  | DSIL  |
        |--------------+-------+-------|
        | reg_idf      |       |   x   |
        | dep_92       |   x   |   x   |
        | arr_nanterre |   x   |   x   |
        |--------------+-------+-------|
        | reg_bfc      |       |   x   |
        | dep_21       |   x   |   x   |
        | arr_dijon    |   x   |   x   |
        |--------------+-------+-------|
        """

        for perimetre in [
            arr_nanterre,
            dep_92,
            region_idf,
            arr_dijon,
            dep_21,
            region_bfc,
        ]:
            SimulationFactory(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DSIL,
                enveloppe__perimetre=perimetre,
            )

        for perimetre in [arr_nanterre, dep_92, arr_dijon, dep_21]:
            SimulationFactory(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DETR,
                enveloppe__perimetre=perimetre,
            )


@pytest.mark.django_db
def test_create_simulation_projets_from_dotation_projet_with_a_detr_and_arrondissement_projet(
    perimetres,
    simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation,
):
    arr_dijon, dep_21, *_ = perimetres

    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        projet__perimetre=arr_dijon,
    )

    DotationProjetService.create_simulation_projets_from_dotation_projet(
        dotation_projet
    )

    # We only have a simulation_projets for enveloppe DETR of this year + the next year and on arr_dijon and dep_21 (because DETR)
    assert dotation_projet.simulationprojet_set.count() == 4
    for annee in [date.today().year, date.today().year + 1]:
        for perimetre in [dep_21, arr_dijon]:
            simulation = Simulation.objects.filter(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DETR,
                enveloppe__perimetre=perimetre,
            ).first()

            simulation_projets = SimulationProjet.objects.filter(
                simulation=simulation, dotation_projet=dotation_projet
            )
            assert simulation_projets.count() == 1

            simulation_projet = simulation_projets.first()
            assert simulation_projet.dotation_projet == dotation_projet
            assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
            assert simulation_projet.montant == 0
            assert simulation_projet.taux == 0

    last_year_simulation_projets = SimulationProjet.objects.filter(
        simulation__enveloppe__annee=date.today().year - 1
    )
    assert last_year_simulation_projets.count() == 0


@pytest.mark.django_db
def test_create_simulation_projets_from_dotation_projet_with_a_dsil_and_departement_projet(
    perimetres,
    simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation,
):
    _, dep_21, region_bfc, *_ = perimetres
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_PROCESSING,
        projet__perimetre=dep_21,
    )

    DotationProjetService.create_simulation_projets_from_dotation_projet(
        dotation_projet
    )

    # We only have a simulation_projets for enveloppe DSIL of this year + the next year and on dep_21 and region_bfc
    assert dotation_projet.simulationprojet_set.count() == 4
    for annee in [date.today().year, date.today().year + 1]:
        for perimetre in [region_bfc, dep_21]:
            simulation = Simulation.objects.filter(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DSIL,
                enveloppe__perimetre=perimetre,
            ).first()

            simulation_projets = SimulationProjet.objects.filter(
                simulation=simulation, dotation_projet=dotation_projet
            )
            assert simulation_projets.count() == 1

            simulation_projet = simulation_projets.first()
            assert simulation_projet.dotation_projet == dotation_projet
            assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
            assert simulation_projet.montant == 0
            assert simulation_projet.taux == 0

    last_year_simulation_projets = SimulationProjet.objects.filter(
        simulation__enveloppe__annee=date.today().year - 1
    )
    assert last_year_simulation_projets.count() == 0


@pytest.mark.django_db
def test_compute_taux_from_montant():
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
    )
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, 10_000)
    assert taux == 10

    dotation_projet = DotationProjetFactory(
        assiette=50_000,
    )
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, 10_000)
    assert taux == 20

    dotation_projet = DotationProjetFactory()
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, 10_000)
    assert taux == 0


def test_get_dotation_projet_status_from_dossier():
    accepted = Dossier(ds_state=Dossier.STATE_ACCEPTE)
    en_construction = Dossier(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    en_instruction = Dossier(ds_state=Dossier.STATE_EN_INSTRUCTION)
    refused = Dossier(ds_state=Dossier.STATE_REFUSE)
    dismissed = Dossier(ds_state=Dossier.STATE_SANS_SUITE)

    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(accepted)
        == PROJET_STATUS_ACCEPTED
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(en_construction)
        == PROJET_STATUS_PROCESSING
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(en_instruction)
        == PROJET_STATUS_PROCESSING
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(refused)
        == PROJET_STATUS_REFUSED
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(dismissed)
        == PROJET_STATUS_DISMISSED
    )

    dossier_unknown = Dossier(ds_state="unknown_state")
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(dossier_unknown)
        is None
    )


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize(
    "dossier_state",
    (
        Dossier.STATE_ACCEPTE,
        Dossier.STATE_EN_CONSTRUCTION,
        Dossier.STATE_EN_INSTRUCTION,
        Dossier.STATE_REFUSE,
        Dossier.STATE_SANS_SUITE,
    ),
)
@pytest.mark.django_db
def test_get_detr_avis_commission(dotation, dossier_state):
    dossier = DossierFactory(
        ds_state=dossier_state,
    )
    avis_commissioin_detr = DotationProjetService.get_detr_avis_commission(
        dotation, dossier
    )
    if dotation == DOTATION_DETR and dossier_state == Dossier.STATE_ACCEPTE:
        assert avis_commissioin_detr is True
    else:
        assert avis_commissioin_detr is None


@pytest.mark.parametrize("field", ("assiette", "finance_cout_total"))
@pytest.mark.parametrize(
    "montant, assiette_or_cout_total, should_raise_exception",
    [
        (50, 100, False),  # Valid montant
        (0, 100, False),  # Valid montant at lower bound
        (100, 100, False),  # Valid montant at upper bound
        (-1, 100, True),  # Invalid montant below lower bound
        (101, 100, True),  # Invalid montant above upper bound
        (None, 100, True),  # Invalid montant as None
        ("invalid", 100, True),  # Invalid montant as string
    ],
)
@pytest.mark.django_db
def test_validate_montant(
    field, montant, assiette_or_cout_total, should_raise_exception
):
    dotation_projet = DotationProjetFactory()
    if field == "finance_cout_total":
        dotation_projet.projet.dossier_ds.finance_cout_total = assiette_or_cout_total
    else:
        dotation_projet.assiette = assiette_or_cout_total

    if should_raise_exception:
        with pytest.raises(
            ValueError,
            match=(
                f"Montant {montant} must be greatear or equal to 0 and less than or "
                f"equal to {dotation_projet.assiette_or_cout_total}"
            ),
        ):
            DotationProjetService.validate_montant(montant, dotation_projet)

    else:
        DotationProjetService.validate_montant(montant, dotation_projet)


test_data = (
    (10_000, 30_000, 33.33),
    (10_000, 0, 0),
    (10_000, 10_000, 100),
    (100_000, 10_000, 100),
    (10_000, -3_000, 0),
    (0, 0, 0),
    (Decimal(0), Decimal(0), 0),
    (0, None, 0),
    (None, 0, 0),
    (1_000, None, 0),
    (None, 4_000, 0),
)


@pytest.mark.parametrize("montant, assiette, expected_taux", test_data)
@pytest.mark.django_db
def test_compute_taux_from_montant_with_various_assiettes(
    assiette, montant, expected_taux
):
    dotation_projet = DotationProjetFactory(assiette=assiette)
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, montant)
    assert taux == round(Decimal(expected_taux), 2)


@pytest.mark.parametrize("montant, cout_total, expected_taux", test_data)
@pytest.mark.django_db
def test_compute_taux_from_montant_with_various_cout_total(
    cout_total, montant, expected_taux
):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=cout_total
    )
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, montant)
    assert taux == round(Decimal(expected_taux), 2)


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
            DotationProjetService.validate_taux(taux)
    else:
        DotationProjetService.validate_taux(taux)

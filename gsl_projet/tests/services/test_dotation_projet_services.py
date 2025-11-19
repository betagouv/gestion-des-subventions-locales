import logging
import re
from datetime import UTC
from decimal import Decimal

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl_core.templatetags.gsl_filters import euro, percent
from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    CritereEligibiliteDetrFactory,
    DossierFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import (
    DotationProjetService as dps,
)
from gsl_projet.tests.factories import (
    CategorieDetrFactory,
    DotationProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory


@pytest.fixture
def perimetres():
    arr_dijon = PerimetreArrondissementFactory()
    dep_21 = PerimetreDepartementalFactory(
        departement=arr_dijon.departement, region=arr_dijon.region
    )
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


@freeze_time("2025-05-06")
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
    field,
    dotation_value,
    dotation_projet_count,
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_assiette_detr=1_000,
        dossier_ds__annotations_assiette_dsil=1_000,
        perimetre=arr_dijon,
    )
    setattr(projet.dossier_ds, field, dotation_value)

    dps.create_or_update_dotation_projet_from_projet(projet)

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
def test_create_or_update_dotation_projet_from_en_instruction_projet_ignore_annotations():
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__annotations_dotation="DETR",
    )
    projet_dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    projet_dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert projet_dotation_projets.count() == 1

    dps.create_or_update_dotation_projet_from_projet(projet)

    projet_dotation_dsil.refresh_from_db()  # always exists

    projet_dotation_projets = DotationProjet.objects.filter(projet_id=projet.id)
    assert projet_dotation_projets.count() == 1

    dsil_dotation_projets = projet_dotation_projets.filter(dotation=DOTATION_DSIL)
    assert dsil_dotation_projets.count() == 1

    detr_dotation_projet = projet_dotation_projets.filter(dotation=DOTATION_DETR)
    assert detr_dotation_projet.count() == 0


@pytest.mark.django_db
def test_create_or_update_dotation_projet_from_projet_also_refuse_dsil_dotation_projet_even_if_not_in_demande_dispositif_sollicite(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    projet = ProjetFactory(
        perimetre=arr_dijon,
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__demande_dispositif_sollicite="DETR",
    )
    projet_dotation_detr = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    projet_dotation_dsil = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
    )
    projet_dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert projet_dotation_projets.count() == 2

    dps.create_or_update_dotation_projet_from_projet(projet)

    projet_dotation_detr.refresh_from_db()  # always exists
    assert projet_dotation_detr.status == PROJET_STATUS_REFUSED

    projet_dotation_dsil.refresh_from_db()  # always exists
    assert projet_dotation_dsil.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DETR, DOTATION_DSIL),
)
def test_create_or_update_dotation_projet_add_detr_categories(dotation):
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
    )
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )
    categorie_detr = CategorieDetrFactory()
    projet.dossier_ds.demande_eligibilite_detr.add(
        CritereEligibiliteDetrFactory(detr_category=categorie_detr)
    )

    # ------

    dps.create_or_update_dotation_projet_from_projet(projet)

    # ------

    assert DotationProjet.objects.count() == 1

    dotation_projet = DotationProjet.objects.first()
    assert dotation_projet.projet == projet
    assert dotation_projet.dotation == dotation
    assert dotation_projet.status == PROJET_STATUS_PROCESSING

    if dotation_projet.dotation == DOTATION_DSIL:
        assert dotation_projet.detr_categories.count() == 0
    else:
        assert categorie_detr in dotation_projet.detr_categories.all()


@pytest.fixture
def simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation(
    perimetres,
):
    arr_nanterre, dep_92, region_idf, arr_dijon, dep_21, region_bfc = perimetres
    for annee in [2024, 2025, 2026]:
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


# @freeze_time("2025-05-06")
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

    dps.create_simulation_projets_from_dotation_projet(dotation_projet)

    # We only have a simulation_projets for enveloppe DETR of this year + the next year and on arr_dijon and dep_21 (because DETR)
    assert dotation_projet.simulationprojet_set.count() == 4
    for annee in [2025, 2026]:
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
        simulation__enveloppe__annee=2024
    )
    assert last_year_simulation_projets.count() == 0


# @freeze_time("2025-05-06")
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

    dps.create_simulation_projets_from_dotation_projet(dotation_projet)

    # We only have a simulation_projets for enveloppe DSIL of this year + the next year and on dep_21 and region_bfc
    assert dotation_projet.simulationprojet_set.count() == 4
    for annee in [2025, 2026]:
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
        simulation__enveloppe__annee=2024
    )
    assert last_year_simulation_projets.count() == 0


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
    avis_commissioin_detr = dps._get_detr_avis_commission(dotation, dossier)
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
                re.escape(
                    f"Le montant {euro(montant)} doit être supérieur ou égal à 0 € et inférieur ou "
                    f"égal à l'assiette ({euro(dotation_projet.assiette_or_cout_total)})."
                )
            ),
        ):
            dps.validate_montant(montant, dotation_projet)

    else:
        dps.validate_montant(montant, dotation_projet)


@pytest.mark.django_db
def test_compute_montant_from_taux():
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
    )
    taux = dps.compute_montant_from_taux(dotation_projet, 25)
    assert taux == 25_000

    dotation_projet = DotationProjetFactory(
        assiette=50_000,
    )
    taux = dps.compute_montant_from_taux(dotation_projet, 25)
    assert taux == 12_500

    dotation_projet = DotationProjetFactory()
    taux = dps.compute_montant_from_taux(dotation_projet, 25)
    assert taux == 0


test_data = (
    (30_000, 33.333, 9_999.90),
    (10_000, 100, 10_000),
    (10_000, 1000, 10_000),
    (-3_000, 10, 0),
    (0, 100, 0),
    (0, 0, 0),
    (Decimal(0), 0, 0),
    (1_000, Decimal(10), 100),
    (None, 0, 0),
    (None, 10, 0),
    (0, None, 0),
    (10, None, 0),
    (4_000, 0, 0),
)


@pytest.mark.parametrize("assiette, taux, expected_montant", test_data)
@pytest.mark.django_db
def test_compute_montant_from_taux_with_various_assiettes(
    assiette, taux, expected_montant
):
    dotation_projet = DotationProjetFactory(assiette=assiette)
    montant = dps.compute_montant_from_taux(dotation_projet, taux)
    assert montant == round(Decimal(expected_montant), 2)


@pytest.mark.parametrize("cout_total, taux, expected_montant", test_data)
@pytest.mark.django_db
def test_compute_montant_from_taux_with_various_cout_total(
    taux, cout_total, expected_montant
):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=cout_total
    )
    montant = dps.compute_montant_from_taux(dotation_projet, taux)
    assert montant == round(Decimal(expected_montant), 2)


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
        with pytest.raises(
            ValueError, match=f"Le taux {percent(taux)} doit être entre 0% and 100%"
        ):
            dps.validate_taux(taux)
    else:
        dps.validate_taux(taux)


class TestGetRootEnveloppeFromDotationProjet:
    @pytest.mark.django_db
    @freeze_time("2025-05-06")
    def test_get_root_enveloppe_from_dotation_projet_with_a_detr_and_arrondissement_projet(
        self, perimetres
    ):
        arr_dijon, dep_21, *_ = perimetres
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            projet__perimetre=arr_dijon,
        )
        dep_detr_enveloppe = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
        _arr_detr_enveloppe = DetrEnveloppeFactory(
            perimetre=arr_dijon, annee=2025, deleguee_by=dep_detr_enveloppe
        )

        enveloppe = dps._get_root_enveloppe_from_dotation_projet(dotation_projet)
        assert enveloppe == dep_detr_enveloppe

    @pytest.mark.django_db
    @freeze_time("2025-05-06")
    def test_get_root_enveloppe_from_dotation_projet_with_a_dsil_and_region_projet(
        self, perimetres
    ):
        arr_dijon, dep_21, region_bfc, *_ = perimetres
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DSIL,
            status=PROJET_STATUS_ACCEPTED,
            projet__perimetre=arr_dijon,
        )
        region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
        dep_dsil_enveloppe_delegated = DsilEnveloppeFactory(
            perimetre=dep_21, annee=2025, deleguee_by=region_dsil_enveloppe
        )
        _arr_dsil_enveloppe_delegated = DsilEnveloppeFactory(
            perimetre=arr_dijon, annee=2025, deleguee_by=dep_dsil_enveloppe_delegated
        )

        enveloppe = dps._get_root_enveloppe_from_dotation_projet(dotation_projet)

        assert enveloppe == region_dsil_enveloppe

    @pytest.mark.django_db
    @freeze_time("2026-05-06")
    def test_get_enveloppe_from_dotation_projet_with_a_next_year_date(
        self, perimetres, caplog
    ):
        arr_dijon, _, region_bfc, *_ = perimetres
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DSIL,
            status=PROJET_STATUS_ACCEPTED,
            projet__perimetre=arr_dijon,
            projet__dossier_ds__ds_date_traitement=timezone.datetime(
                2026, 1, 15, tzinfo=UTC
            ),
        )
        _region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

        with pytest.raises(Enveloppe.DoesNotExist):  # No enveloppe for 2026
            dps._get_root_enveloppe_from_dotation_projet(dotation_projet)

        record = caplog.records[0]
        assert record.message == "No enveloppe found for a dotation projet"
        assert record.levelname == "WARNING"
        assert (
            getattr(record, "dossier_ds_number", None)
            == dotation_projet.dossier_ds.ds_number
        )
        assert getattr(record, "dotation", None) == dotation_projet.dotation
        assert getattr(record, "year", None) == 2026
        assert getattr(record, "perimetre", None) == arr_dijon


@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "value, expected_dotation",
    [
        ("DETR", [DOTATION_DETR]),
        ("DSIL", [DOTATION_DSIL]),
        ("[DETR, DSIL]", [DOTATION_DETR, DOTATION_DSIL]),
        ("DETR et DSIL", [DOTATION_DETR, DOTATION_DSIL]),
        ("['DETR', 'DSIL', 'DETR et DSIL']", [DOTATION_DETR, DOTATION_DSIL]),
    ],
)
@pytest.mark.django_db
def test_get_dotations_from_field(field, value, expected_dotation):
    projet = ProjetFactory()
    setattr(projet.dossier_ds, field, value)
    dotation = dps._get_dotations_from_field(projet, field)
    assert dotation == expected_dotation


# ========== DUN tests ==========


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_accepted_with_annotations_dotation(
    perimetres,
):
    """Test _initialize_dotation_projets_from_projet_accepted when annotations_dotation is set"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_dotation="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=20_000,
        dossier_ds__annotations_montant_accorde_detr=5_000,
        dossier_ds__annotations_montant_accorde_dsil=15_000,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dotation_projets = dps._initialize_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED
    assert detr_dp.assiette == 10_000
    assert detr_dp.detr_avis_commission is True
    assert detr_dp.montant_retenu == 5_000
    assert detr_dp.taux_retenu == 50

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_ACCEPTED
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.detr_avis_commission is None
    assert dsil_dp.montant_retenu == 15_000
    assert dsil_dp.taux_retenu == 75


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_accepted_with_empty_annotations_dotation_falls_back_to_demande_dispositif_sollicite(
    perimetres, caplog
):
    """Test _initialize_dotation_projets_from_projet_accepted when annotations_dotation is empty, falls back to demande_dispositif_sollicite"""

    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_dotation="",  # Empty
        dossier_ds__demande_dispositif_sollicite="DETR",
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_montant_accorde_detr=None,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    with caplog.at_level(logging.WARNING):
        dotation_projets = dps._initialize_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 1
    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED
    assert detr_dp.assiette is None
    assert detr_dp.montant_retenu == 0
    assert detr_dp.taux_retenu == 0
    assert detr_dp.detr_avis_commission is True
    assert detr_dp.programmation_projet is not None
    assert detr_dp.programmation_projet.status == PROJET_STATUS_ACCEPTED

    # Check log message, level and extra
    assert len(caplog.records) == 4
    record = caplog.records[0]
    assert record.message == "No dotation"
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "projet", None) == projet.pk
    assert getattr(record, "value", None) == ""
    assert getattr(record, "field", None) == "annotations_dotation"

    record = caplog.records[1]
    assert (
        record.message
        == "No dotations found in annotations_dotation for accepted dossier during initialisation"
    )
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "projet", None) == projet.pk

    record = caplog.records[2]
    assert record.message == "Assiette is missing in dossier annotations"
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "dotation", None) == DOTATION_DETR

    record = caplog.records[3]
    assert record.message == "Montant is missing in dossier annotations"
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "dotation", None) == DOTATION_DETR


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_refused(perimetres):
    """Test _initialize_dotation_projets_from_projet_refused"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__demande_dispositif_sollicite="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=None,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dotation_projets = dps._initialize_dotation_projets_from_projet_refused(projet)

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_REFUSED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 0
    assert detr_dp.taux_retenu == 0
    assert detr_dp.detr_avis_commission is None
    assert detr_dp.programmation_projet is not None
    assert detr_dp.programmation_projet.status == PROJET_STATUS_REFUSED

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_REFUSED
    assert dsil_dp.assiette is None
    assert dsil_dp.montant_retenu == 0
    assert dsil_dp.taux_retenu == 0
    assert dsil_dp.detr_avis_commission is None
    assert dsil_dp.programmation_projet is not None
    assert dsil_dp.programmation_projet.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_initialize_dotation_projets_from_projet_sans_suite(perimetres):
    """Test _initialize_dotation_projets_from_projet_sans_suite"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__demande_dispositif_sollicite="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=None,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dotation_projets = dps._initialize_dotation_projets_from_projet_sans_suite(projet)

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_DISMISSED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 0
    assert detr_dp.taux_retenu == 0

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_DISMISSED
    assert dsil_dp.assiette is None
    assert dsil_dp.montant_retenu == 0
    assert dsil_dp.taux_retenu == 0


@pytest.mark.django_db
def test_initialize_dotation_projets_from_projet_en_construction_or_instruction():
    """Test _initialize_dotation_projets_from_projet_en_construction_or_instruction"""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_CONSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=20_000,
    )

    dotation_projets = (
        dps._initialize_dotation_projets_from_projet_en_construction_or_instruction(
            projet
        )
    )

    assert len(dotation_projets) == 2
    assert DotationProjet.objects.filter(projet=projet).count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_PROCESSING
    assert detr_dp.assiette is None
    assert detr_dp.montant_retenu is None
    assert not hasattr(detr_dp, "programmation_projet")

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_PROCESSING
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.montant_retenu is None
    assert not hasattr(dsil_dp, "programmation_projet")


## Test Update Dotation Projets


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_accepted_creates_new_dotation_projets(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_accepted creates new dotation projets"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__demande_dispositif_sollicite="DETR",
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_montant_accorde_detr=None,
        dossier_ds__ds_date_traitement=None,
        perimetre=arr_dijon,
    )

    dps._initialize_dotation_projets_from_projet(projet)
    assert projet.dotationprojet_set.count() == 1

    # Projet has been accepted on DS for DETR and DSIL
    projet.dossier_ds.annotations_dotation = "DETR et DSIL"
    projet.dossier_ds.annotations_assiette_detr = 10_000
    projet.dossier_ds.annotations_montant_accorde_detr = 5_000
    projet.dossier_ds.annotations_assiette_dsil = 20_000
    projet.dossier_ds.annotations_montant_accorde_dsil = 15_000
    projet.dossier_ds.ds_date_traitement = timezone.datetime(2025, 1, 15, tzinfo=UTC)
    projet.dossier_ds.save()

    dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 2
    assert projet.dotationprojet_set.count() == 2

    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED
    assert detr_dp.assiette == 10_000
    assert detr_dp.montant_retenu == 5_000
    assert detr_dp.taux_retenu == 50

    dsil_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DSIL)
    assert dsil_dp.status == PROJET_STATUS_ACCEPTED
    assert dsil_dp.assiette == 20_000
    assert dsil_dp.montant_retenu == 15_000
    assert dsil_dp.taux_retenu == 75


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_accepted_removes_dotation_projets(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_accepted removes dotation projets not in annotations_dotation"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_dotation="DETR et DSIL",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_assiette_dsil=20_000,
        dossier_ds__annotations_montant_accorde_detr=5_000,
        dossier_ds__annotations_montant_accorde_dsil=15_000,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    dps._initialize_dotation_projets_from_projet(projet)
    assert projet.dotationprojet_set.count() == 2

    # Update to remove DSIL
    projet.dossier_ds.annotations_dotation = "DETR"
    projet.dossier_ds.save()

    dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 1
    assert projet.dotationprojet_set.count() == 1
    assert DotationProjet.objects.filter(projet=projet, dotation=DOTATION_DETR).exists()
    assert not DotationProjet.objects.filter(
        projet=projet, dotation=DOTATION_DSIL
    ).exists()


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_accepted_with_empty_annotations_dotation_falls_back(
    perimetres,
    caplog,
):
    """Test _update_dotation_projets_from_projet_accepted falls back to demande_dispositif_sollicite when annotations_dotation is empty"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        dossier_ds__annotations_dotation="",
        dossier_ds__demande_dispositif_sollicite="DETR",
        dossier_ds__annotations_assiette_detr=10_000,
        dossier_ds__annotations_montant_accorde_detr=5_000,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    with caplog.at_level(logging.WARNING):
        dotation_projets = dps._update_dotation_projets_from_projet_accepted(projet)

    assert len(dotation_projets) == 1
    detr_dp = DotationProjet.objects.get(projet=projet, dotation=DOTATION_DETR)
    assert detr_dp.status == PROJET_STATUS_ACCEPTED

    assert len(caplog.records) == 2
    record = caplog.records[0]
    assert record.message == "No dotation"
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "projet", None) == projet.pk

    record = caplog.records[1]
    assert (
        record.message
        == "No dotations found in annotations_dotation for accepted dossier during update"
    )
    assert record.levelname == "WARNING"
    assert getattr(record, "dossier_ds_number", None) == projet.dossier_ds.ds_number
    assert getattr(record, "projet", None) == projet.pk


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_refused(perimetres):
    """Test _update_dotation_projets_from_projet_refused"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    # Create existing dotation projets with different statuses
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_refused(projet)

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_REFUSED

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_refused_does_not_update_already_refused(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_refused does not update already refused dotation projets"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_REFUSE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    # Create already refused dotation projet
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_refused(projet)

    assert len(dotation_projets) == 1
    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_sans_suite(perimetres):
    """Test _update_dotation_projets_from_projet_sans_suite"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    # Create existing dotation projets with different statuses
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_sans_suite(projet)

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_DISMISSED

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_DISMISSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_sans_suite_does_not_update_already_dismissed_or_refused(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_sans_suite does not update already dismissed or refused dotation projets"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 15, tzinfo=UTC),
        perimetre=arr_dijon,
    )

    # Create already dismissed and refused dotation projets
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_DISMISSED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_REFUSED
    )

    dotation_projets = dps._update_dotation_projets_from_projet(projet)

    assert len(dotation_projets) == 2
    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_DISMISSED
    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_update_dotation_projets_from_projet_back_to_instruction(perimetres):
    """Test _update_dotation_projets_from_projet_back_to_instruction"""
    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 10, tzinfo=UTC),
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, tzinfo=UTC
        ),
    )

    # Create dotation projets with different statuses
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_REFUSED
    )

    dotation_projets = dps._update_dotation_projets_from_projet(projet)

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_PROCESSING

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_REFUSED


@pytest.mark.django_db
def test_update_dotation_projets_from_projet_back_to_instruction_with_one_accepted_and_one_dismissed(
    perimetres,
):
    """Test _update_dotation_projets_from_projet_back_to_instruction with one accepted and one dismissed"""
    arr_dijon, dep_21, region_bfc, *_ = perimetres

    projet = ProjetFactory(
        dossier_ds__ds_state=Dossier.STATE_EN_INSTRUCTION,
        dossier_ds__ds_date_traitement=timezone.datetime(2025, 1, 10, tzinfo=UTC),
        dossier_ds__ds_date_passage_en_instruction=timezone.datetime(
            2025, 1, 15, tzinfo=UTC
        ),
        perimetre=arr_dijon,
    )

    # Create one accepted and one dismissed dotation projet
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_DISMISSED
    )

    dotation_projets = dps._update_dotation_projets_from_projet_back_to_instruction(
        projet
    )

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_PROCESSING

    dsil_dp.refresh_from_db()
    # The dismissed one should remain dismissed (not updated)
    assert dsil_dp.status == PROJET_STATUS_DISMISSED


@pytest.mark.django_db
def test_update_dotation_projets_with_one_accepted_and_one_dismissed_or_refused():
    """Test _update_dotation_projets_with_one_accepted_and_one_dismissed_or_refused"""
    projet = ProjetFactory()

    # Create one accepted and one dismissed dotation projet
    detr_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    dsil_dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_DISMISSED
    )

    dotation_projets = (
        dps._update_dotation_projets_with_one_accepted_and_one_dismissed_or_refused(
            projet
        )
    )

    assert len(dotation_projets) == 2

    detr_dp.refresh_from_db()
    assert detr_dp.status == PROJET_STATUS_PROCESSING

    dsil_dp.refresh_from_db()
    assert dsil_dp.status == PROJET_STATUS_DISMISSED  # Not changed


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_assiette_from_dossier_handles_missing_assiette(caplog):
    """Test _get_assiette_from_dossier handles missing assiette"""
    projet = ProjetFactory(
        dossier_ds__annotations_assiette_detr=None,
        dossier_ds__annotations_assiette_dsil=None,
    )

    assiette_detr = dps._get_assiette_from_dossier(projet.dossier_ds, DOTATION_DETR)
    assert assiette_detr is None

    assiette_dsil = dps._get_assiette_from_dossier(projet.dossier_ds, DOTATION_DSIL)
    assert assiette_dsil is None

    # Check that warnings were logged
    assert len(caplog.records) == 2
    assert "Assiette is missing" in caplog.records[0].message


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_get_montant_from_dossier_handles_missing_montant(caplog):
    """Test _get_montant_from_dossier handles missing montant"""
    projet = ProjetFactory(
        dossier_ds__annotations_montant_accorde_detr=None,
        dossier_ds__annotations_montant_accorde_dsil=None,
    )

    montant_detr = dps._get_montant_from_dossier(projet.dossier_ds, DOTATION_DETR)
    assert montant_detr == 0

    montant_dsil = dps._get_montant_from_dossier(projet.dossier_ds, DOTATION_DSIL)
    assert montant_dsil == 0

    # Check that warnings were logged
    assert len(caplog.records) == 2
    assert "Montant is missing" in caplog.records[0].message

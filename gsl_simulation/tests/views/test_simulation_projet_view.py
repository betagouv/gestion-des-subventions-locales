from decimal import Decimal

import pytest

from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import (
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl_simulation.tests.factories import SimulationProjetFactory
from gsl_simulation.views.simulation_projet_views import (
    _get_other_dotation_montants,
)

pytestmark = pytest.mark.django_db


def test_get_other_dotation_montants_without_double_dotations():
    """Test that function returns None when projet doesn't have double dotations."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(projet=projet)
    simulation_projet = SimulationProjetFactory(dotation_projet=dsil_dotation_projet)

    result = _get_other_dotation_montants(simulation_projet)

    assert result is None


def test_get_other_dotation_montants_dsil_to_detr_without_programmation():
    """Test DSIL -> DETR direction when other dotation has no programmation."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("10000.00")
    )
    DetrProjetFactory(projet=projet, assiette=Decimal("20000.00"))
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("5000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DETR
    assert result["assiette"] == Decimal("20000.00")
    assert result["montant"] is None
    assert result["taux"] is None


def test_get_other_dotation_montants_detr_to_dsil_without_programmation():
    """Test DETR -> DSIL direction when other dotation has no programmation."""
    projet = ProjetFactory()
    detr_dotation_projet = DetrProjetFactory(
        projet=projet, assiette=Decimal("15000.00")
    )
    DsilProjetFactory(projet=projet, assiette=Decimal("25000.00"))
    simulation_projet = SimulationProjetFactory(
        dotation_projet=detr_dotation_projet, montant=Decimal("8000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DSIL
    assert result["assiette"] == Decimal("25000.00")
    assert result["montant"] is None
    assert result["taux"] is None


def test_get_other_dotation_montants_dsil_to_detr_with_programmation():
    """Test DSIL -> DETR direction when other dotation has programmation."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("10000.00")
    )
    detr_dotation_projet = DetrProjetFactory(
        projet=projet, assiette=Decimal("20000.00")
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=detr_dotation_projet, montant=Decimal("15000.00")
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("5000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DETR
    assert result["assiette"] == Decimal("20000.00")
    assert result["montant"] == Decimal("15000.00")
    assert result["taux"] == programmation_projet.taux


def test_get_other_dotation_montants_detr_to_dsil_with_programmation():
    """Test DETR -> DSIL direction when other dotation has programmation."""
    projet = ProjetFactory()
    detr_dotation_projet = DetrProjetFactory(
        projet=projet, assiette=Decimal("15000.00")
    )
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("25000.00")
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("20000.00")
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=detr_dotation_projet, montant=Decimal("8000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DSIL
    assert result["assiette"] == Decimal("25000.00")
    assert result["montant"] == Decimal("20000.00")
    assert result["taux"] == programmation_projet.taux


def test_get_other_dotation_montants_with_none_assiette():
    """Test that function handles None assiette correctly."""
    projet = ProjetFactory()
    dsil_dotation_projet = DsilProjetFactory(
        projet=projet, assiette=Decimal("10000.00")
    )
    DetrProjetFactory(projet=projet, assiette=None)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dsil_dotation_projet, montant=Decimal("5000.00")
    )

    result = _get_other_dotation_montants(simulation_projet)

    assert result is not None
    assert result["dotation"] == DOTATION_DETR
    assert result["assiette"] is None
    assert result["montant"] is None
    assert result["taux"] is None

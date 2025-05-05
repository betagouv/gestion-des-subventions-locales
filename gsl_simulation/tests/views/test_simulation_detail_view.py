import pytest

from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory
from gsl_simulation.views.simulation_views import SimulationDetailView


@pytest.fixture
def one_dotation_projets():
    DotationProjetFactory.create_batch(2, dotation=DOTATION_DSIL)


@pytest.mark.django_db
def test_get_other_dotations_simulation_projet_no_double_dotation(one_dotation_projets):
    projets = Projet.objects.all()
    assert projets.count() == 2

    view = SimulationDetailView()

    result = view._get_other_dotations_simulation_projet(projets, DOTATION_DSIL)

    assert result == {}


@pytest.fixture
def double_dotation_projet():
    projet = ProjetFactory()
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    return projet


@pytest.mark.django_db
def test_get_other_dotations_simulation_projet(
    double_dotation_projet, one_dotation_projets
):
    projets = Projet.objects.all()
    assert projets.count() == 3
    assert DotationProjet.objects.filter(dotation=DOTATION_DSIL).count() == 3
    assert DotationProjet.objects.filter(dotation=DOTATION_DETR).count() == 1

    for dp in DotationProjet.objects.all():
        SimulationProjetFactory(dotation_projet=dp)

    view = SimulationDetailView()

    result = view._get_other_dotations_simulation_projet(projets, DOTATION_DSIL)

    detr_simulation_projet = SimulationProjet.objects.filter(
        dotation_projet__projet=double_dotation_projet,
        dotation_projet__dotation=DOTATION_DETR,
    )
    assert detr_simulation_projet.count() == 1
    assert result == {
        double_dotation_projet.id: detr_simulation_projet.first(),
    }


@pytest.mark.django_db
def test_get_other_dotations_simulation_projet_without_other_simulation_projet(
    double_dotation_projet, one_dotation_projets
):
    projets = Projet.objects.all()
    assert projets.count() == 3
    assert DotationProjet.objects.filter(dotation=DOTATION_DSIL).count() == 3
    assert DotationProjet.objects.filter(dotation=DOTATION_DETR).count() == 1

    view = SimulationDetailView()

    result = view._get_other_dotations_simulation_projet(projets, DOTATION_DSIL)

    assert result == {
        double_dotation_projet.id: None,
    }

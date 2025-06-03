import csv
import io

import pytest
from django.urls import resolve, reverse
from freezegun import freeze_time

from gsl_core.tests.factories import (
    RequestFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.tests.factories import (
    DotationProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_simulation.views.simulation_views import (
    FilteredProjetsExportView,
    SimulationDetailView,
)


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


@freeze_time("2025-05-26")
@pytest.mark.django_db
def test_get_filter_projets_csv_export_view():
    ### Arrange
    simulation = SimulationFactory(
        title="Ma Simulation", enveloppe__dotation=DOTATION_DSIL
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet__dotation=DOTATION_DSIL,
        simulation=simulation,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory.create_batch(
        3,
        dotation_projet__dotation=DOTATION_DSIL,
        simulation=simulation,
        status=SimulationProjet.STATUS_REFUSED,
    )
    projets = Projet.objects.all()
    assert projets.count() == 5

    ### Act
    req = RequestFactory()
    view = FilteredProjetsExportView()
    url = reverse(
        "simulation:simulation-projets-export",
        kwargs={"slug": simulation.slug, "type": "csv"},
    )
    request = req.get(url, data={"status": [SimulationProjet.STATUS_ACCEPTED]})
    request.resolver_match = resolve(url)
    view.request = request
    view.kwargs = {"slug": simulation.slug}
    response = view.get(request)

    ### Assert
    assert response.status_code == 200
    assert response["Content-Disposition"] == (
        'attachment; filename="2025-05-26 simulation Ma Simulation.csv"'
    )
    assert response["Content-Type"] == "text/csv"

    csv_content = response.content.decode("utf-8")
    csv_lines = list(csv.reader(io.StringIO(csv_content)))
    assert len(csv_lines) == 3  # 1 header + 2 projets acceptés

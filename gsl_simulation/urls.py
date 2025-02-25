from django.urls import path

from gsl_simulation.views import simulation_views
from gsl_simulation.views.decorators import simulation_must_be_visible_by_user
from gsl_simulation.views.simulation_projet_views import (
    patch_montant_simulation_projet,
    patch_status_simulation_projet,
    patch_taux_simulation_projet,
)

urlpatterns = [
    path(
        "simulations/",
        simulation_views.SimulationListView.as_view(),
        name="simulation-list",
    ),
    path(
        "simulation/<slug:slug>/",
        simulation_must_be_visible_by_user(
            simulation_views.SimulationDetailView.as_view()
        ),
        name="simulation-detail",
    ),
    path(
        "modifier-le-taux-d-un-projet-de-simulation/<int:pk>/",
        patch_taux_simulation_projet,
        name="patch-simulation-projet-taux",
    ),
    path(
        "modifier-le-montant-un-projet-de-simulation/<int:pk>/",
        patch_montant_simulation_projet,
        name="patch-simulation-projet-montant",
    ),
    path(
        "modifier-le-statut-d-un-projet-de-simulation/<int:pk>/",
        patch_status_simulation_projet,
        name="patch-simulation-projet-status",
    ),
    path(
        "creation-simulation",
        simulation_views.simulation_form,
        name="simulation-form",
    ),
]

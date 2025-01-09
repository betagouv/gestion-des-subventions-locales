from django.urls import path

from . import views

urlpatterns = [
    path(
        "simulations/",
        views.SimulationListView.as_view(),
        name="simulation_list",
    ),
    path(
        "simulation/<slug:slug>/",
        views.SimulationDetailView.as_view(),
        name="simulation_detail",
    ),
    path(
        "modifier-le-taux-d-un-projet-de-simulation/",
        views.patch_taux_simulation_projet,
        name="patch-simulation-projet-taux",
    ),
    path(
        "modifier-le-montant-un-projet-de-simulation/",
        views.patch_montant_simulation_projet,
        name="patch-simulation-projet-montant",
    ),
    path(
        "modifier-le-statut-d-un-projet-de-simulation/",
        views.patch_status_simulation_projet,
        name="patch-simulation-projet-status",
    ),
]

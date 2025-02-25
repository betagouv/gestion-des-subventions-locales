from django.urls import path

from . import views

urlpatterns = [
    path(
        "simulations/",
        views.SimulationListView.as_view(),
        name="simulation-list",
    ),
    path(
        "simulation/<slug:slug>/",
        views.simulation_must_be_visible_by_user(views.SimulationDetailView.as_view()),
        name="simulation-detail",
    ),
    path(
        "modifier-le-taux-d-un-projet-de-simulation/<int:pk>/",
        views.patch_taux_simulation_projet,
        name="patch-simulation-projet-taux",
    ),
    path(
        "modifier-le-montant-un-projet-de-simulation/<int:pk>/",
        views.patch_montant_simulation_projet,
        name="patch-simulation-projet-montant",
    ),
    path(
        "modifier-le-statut-d-un-projet-de-simulation/<int:pk>/",
        views.patch_status_simulation_projet,
        name="patch-simulation-projet-status",
    ),
    path(
        "creation-simulation",
        views.simulation_form,
        name="simulation-form",
    ),
]

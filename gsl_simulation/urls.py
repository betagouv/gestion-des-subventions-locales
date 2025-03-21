from django.urls import path

from gsl_simulation.views import simulation_views
from gsl_simulation.views.decorators import (
    simulation_must_be_visible_by_user,
    simulation_projet_must_be_visible_by_user,
)
from gsl_simulation.views.simulation_projet_views import (
    SimulationProjetDetailView,
    patch_avis_commission_detr_simulation_projet,
    patch_is_budget_vert_simulation_projet,
    patch_is_qpv_and_is_attached_to_a_crte_simulation_projet,
    patch_montant_simulation_projet,
    patch_status_simulation_projet,
    patch_taux_simulation_projet,
)

urlpatterns = [
    path(
        "liste/",
        simulation_views.SimulationListView.as_view(),
        name="simulation-list",
    ),
    path(
        "voir/<slug:slug>/",
        simulation_must_be_visible_by_user(
            simulation_views.SimulationDetailView.as_view()
        ),
        name="simulation-detail",
    ),
    path(
        "projet-detail/<int:pk>/",
        simulation_projet_must_be_visible_by_user(SimulationProjetDetailView.as_view()),
        name="simulation-projet-detail",
    ),
    path(
        "projet-detail/<int:pk>/<str:tab>/",
        simulation_projet_must_be_visible_by_user(SimulationProjetDetailView.as_view()),
        name="simulation-projet-tab",
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
        "modifier-l-avis-commission-detr-d-un-projet-de-simulation/<int:pk>/",
        patch_avis_commission_detr_simulation_projet,
        name="patch-avis-commission-detr-simulation-projet",
    ),
    path(
        "modifier-budget-vert-d-un-projet-de-simulation/<int:pk>/",
        patch_is_budget_vert_simulation_projet,
        name="patch-is-budget-vert-simulation-projet",
    ),
    path(
        "modifier-qpv-et-crte-d-un-projet-de-simulation/<int:pk>/",
        patch_is_qpv_and_is_attached_to_a_crte_simulation_projet,
        name="patch-is-qpv-and-is-attached-to-a-crte-simulation-projet",
    ),
    path(
        "creation-simulation",
        simulation_views.simulation_form,
        name="simulation-form",
    ),
]

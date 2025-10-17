from django.urls import path

from gsl_simulation.views import simulation_views
from gsl_simulation.views.decorators import (
    simulation_must_be_visible_by_user,
)
from gsl_simulation.views.simulation_projet_annotations_views import (
    ProjetNoteEditView,
    SimulationProjetAnnotationsView,
    get_note_card,
)
from gsl_simulation.views.simulation_projet_views import (
    ProjetFormView,
    RefuseProjetModalView,
    SimulationProjetDetailView,
    patch_dotation_projet,
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
        "voir/<slug:slug>/<str:type>/",
        simulation_must_be_visible_by_user(
            simulation_views.FilteredProjetsExportView.as_view()
        ),
        name="simulation-projets-export",
    ),
    path(
        "projet-detail/<int:pk>/",
        SimulationProjetDetailView.as_view(),
        name="simulation-projet-detail",
    ),
    path(
        "projet-detail/<int:pk>/annotations/",
        SimulationProjetAnnotationsView.as_view(),
        name="simulation-projet-annotations",
    ),
    path(
        # careful when tab="annotations" it actually matches SimulationProjetAnnotationsView just above
        # lost 20 minutes trying to solve a bug on SimulationProjetDetailView that didn't exist
        "projet-detail/<int:pk>/<str:tab>/",
        SimulationProjetDetailView.as_view(),
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
        "<int:pk>/refuser/",
        RefuseProjetModalView.as_view(),
        name="refuse-form",
    ),
    path(
        "creation-simulation",
        simulation_views.simulation_form,
        name="simulation-form",
    ),
    path(
        "modifier-le-projet-d-un-projet-de-simulation/<int:pk>/",
        ProjetFormView.as_view(),
        name="patch-projet",
    ),
    path(
        "modifier-le-projet-de-dotation-d-un-projet-de-simulation/<int:pk>/",
        patch_dotation_projet,
        name="patch-dotation-projet",
    ),
    # Annotations
    path(
        "simulation_projet/<int:pk>/annotations/<int:note_id>/edit",
        ProjetNoteEditView.as_view(),
        name="get-edit-projet-note",
    ),
    path(
        "simulation_projet/<int:pk>/annotations/<int:note_id>",
        get_note_card,
        name="get-note-card",
    ),
]

from django.urls import path

from gsl_programmation.views import (
    ProgrammationProjetDetailView,
    ProgrammationProjetListView,
)

app_name = "gsl_programmation"

urlpatterns = [
    path(
        "liste/",
        ProgrammationProjetListView.as_view(),
        name="programmation-projet-list",
    ),
    path(
        "liste/<str:dotation>/",
        ProgrammationProjetListView.as_view(),
        name="programmation-projet-list-dotation",
    ),
    path(
        "voir/<int:programmation_projet_id>/",
        ProgrammationProjetDetailView.as_view(),
        name="programmation-projet-detail",
    ),
    path(
        "voir/<int:programmation_projet_id>/<str:tab>/",
        ProgrammationProjetDetailView.as_view(),
        name="programmation-projet-tab",
    ),
]

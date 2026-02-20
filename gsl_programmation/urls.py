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
        "voir/<int:projet_id>/",
        ProgrammationProjetDetailView.as_view(),
        name="programmation-projet-detail",
    ),
    path(
        "voir/<int:projet_id>/notes/",
        ProgrammationProjetDetailView.as_view(tab_name="notes"),
        name="programmation-projet-notes",
    ),
]

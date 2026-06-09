from django.urls import path

from gsl_programmation.views import ProgrammationProjetListView

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
]

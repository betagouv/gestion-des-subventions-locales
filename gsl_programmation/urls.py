from django.urls import path

from gsl_programmation.views import ProgrammationListView

app_name = "gsl_programmation"

urlpatterns = [
    path(
        "liste/",
        ProgrammationListView.as_view(),
        name="programmation-projet-list",
    ),
    path(
        "liste/<str:dotation>/",
        ProgrammationListView.as_view(),
        name="programmation-projet-list-dotation",
    ),
]

from django.urls import path

from gsl.programmation.views import ProgrammationListView

app_name = "gsl_programmation"

urlpatterns = [
    path(
        "liste/<int:campagne>/",
        ProgrammationListView.as_view(),
        name="programmation-projet-list",
    ),
    path(
        "liste/<str:dotation>/<int:campagne>/",
        ProgrammationListView.as_view(),
        name="programmation-projet-list-dotation",
    ),
]

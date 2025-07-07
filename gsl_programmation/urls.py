from django.urls import path

from . import views

app_name = "gsl_programmation"

urlpatterns = [
    path(
        "liste/",
        views.ProgrammationProjetListView.as_view(),
        name="programmation-projets-list",
    ),
]

from django.urls import path

from . import views

urlpatterns = [
    path(
        "simulations/",
        views.ScenarioListView.as_view(),
        name="scenario_list",
    ),
    path(
        "simulation/<slug:slug>/",
        views.ScenarioDetailView.as_view(),
        name="scenario_detail",
    ),
]

from django.urls import path

from . import views

urlpatterns = [
    path(
        "simulations/",
        views.SimulationListView.as_view(),
        name="simulation_list",
    ),
    path(
        "simulation/<slug:slug>/",
        views.SimulationDetailView.as_view(),
        name="simulation_detail",
    ),
]

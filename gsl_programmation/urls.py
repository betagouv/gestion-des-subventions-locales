from django.urls import path

from . import views

urlpatterns = [
    path(
        "simulation/<slug:slug>/",
        views.ScenarioDetailView.as_view(),
        name="scenario_detail",
    )
]

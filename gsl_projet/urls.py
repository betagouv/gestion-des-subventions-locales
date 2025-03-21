from django.urls import path

from . import views

urlpatterns = [
    path(
        "voir/<int:projet_id>/",
        views.get_projet,
        name="get-projet",
    ),
    path(
        "voir/<int:projet_id>/<str:tab>/",
        views.get_projet_tab,
        name="get-projet-tab",
    ),
    path("liste", views.ProjetListView.as_view(), name="list"),
]

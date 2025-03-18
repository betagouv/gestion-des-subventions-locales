from django.urls import path

from . import views

urlpatterns = [
    path(
        "voir/<int:projet_id>/",
        views.get_projet,
        name="get-projet",
    ),
    path(
        "voir/<int:projet_id>/annotations/",
        views.get_projet_annotations,
        name="get-projet-annotations",
    ),
    path(
        "voir/<int:projet_id>/demandeur/",
        views.get_projet_demandeur,
        name="get-projet-demandeur",
    ),
    path(
        "voir/<int:projet_id>/historique_demandeur/",
        views.get_projet_historique_demandeur,
        name="get-projet-historique",
    ),
    path("liste", views.ProjetListView.as_view(), name="list"),
]

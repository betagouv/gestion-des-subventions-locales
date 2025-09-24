from django.urls import path

from gsl_programmation.views import (
    EnveloppeCreateView,
    EnveloppeDeleteView,
    EnveloppeUpdateView,
)

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
    path(
        "enveloppe/ajouter/",
        EnveloppeCreateView.as_view(),
        name="enveloppe-create",
    ),
    path(
        "enveloppe/<int:pk>/modifier/",
        EnveloppeUpdateView.as_view(),
        name="enveloppe-update",
    ),
    path(
        "enveloppe/<int:pk>/supprimer/",
        EnveloppeDeleteView.as_view(),
        name="enveloppe-delete",
    ),
]

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
        "voir/<int:projet_id>/notes/",
        views.get_projet_notes,
        name="get-projet-notes",
    ),
    path(
        "voir/<int:projet_id>/notes/commentaire/",
        views.ProjetCommentUpdateView.as_view(),
        name="update-projet-comment",
    ),
    path("liste", views.ProjetListView.as_view(), name="list"),
    path(
        "liste/annotations-manquantes",
        views.ProjetMissingAnnotationsListView.as_view(),
        name="missing-annotations-list",
    ),
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

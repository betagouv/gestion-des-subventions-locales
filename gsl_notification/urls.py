from django.urls import path

from gsl_notification.views.views import (
    CreateModelArreteWizard,
    ModeleArreteListView,
    change_arrete_view,
    create_arrete_signe_view,
    delete_arrete_signe_view,
    delete_arrete_view,
    # create_arrete_view,
    documents_view,
    download_arrete,
    download_arrete_signe,
)

urlpatterns = [
    path(
        "<int:programmation_projet_id>/documents/",
        documents_view,
        name="documents",
    ),
    # path(
    #     "<int:programmation_projet_id>/creer-arrete/",
    #     create_arrete_view,
    #     name="create-arrete",
    # ),
    path(
        "<int:programmation_projet_id>/modifier-arrete/",
        change_arrete_view,
        name="modifier-arrete",
    ),
    path(
        "arrete/<int:arrete_id>/download/",
        download_arrete,
        name="arrete-download",
    ),
    path(
        "arrete/<int:arrete_id>/delete/",
        delete_arrete_view,
        name="delete-arrete",
    ),
    path(
        "arrete-signe/<int:arrete_signe_id>/delete/",
        delete_arrete_signe_view,
        name="delete-arrete-signe",
    ),
    path(
        "<int:programmation_projet_id>/creer-arrete-signe/",
        create_arrete_signe_view,
        name="create-arrete-signe",
    ),
    path(
        "arrete-signe/<int:arrete_signe_id>/download/",
        download_arrete_signe,
        name="arrete-signe-download",
    ),
    path(
        "modeles/liste/<str:dotation>",
        ModeleArreteListView.as_view(),
        name="modele-arrete-liste",
    ),
    path(
        "modeles/nouveau/<str:dotation>/",
        CreateModelArreteWizard.as_view(),
        name="modele-arrete-creer",
    ),
]

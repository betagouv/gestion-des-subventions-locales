from django.urls import path

from gsl_notification.views.decorators import (
    arrete_visible_by_user,
)
from gsl_notification.views.modele_arrete_views import (
    CreateModelArreteWizard,
    DuplicateModeleArrete,
    ModeleArreteListView,
    UpdateModeleArrete,
    delete_modele_arrete_view,
)
from gsl_notification.views.views import (
    DownloadArreteView,
    PrintArreteView,
    change_arrete_view,
    create_arrete_signe_view,
    delete_arrete_signe_view,
    delete_arrete_view,
    documents_view,
    download_arrete_signe,
    select_modele,
    view_arrete_signe,
)

urlpatterns = [
    path(
        "<int:programmation_projet_id>/documents/",
        documents_view,
        name="documents",
    ),
    # Arretes
    path(
        "<int:programmation_projet_id>/selection-d-un-modele/",
        select_modele,
        name="select-modele",
    ),
    path(
        "<int:programmation_projet_id>/modifier-arrete/",
        change_arrete_view,
        name="modifier-arrete",
    ),
    path(
        "arrete/<int:arrete_id>/download/",
        arrete_visible_by_user(DownloadArreteView.as_view()),
        name="arrete-download",
    ),
    path(
        "arrete/<int:arrete_id>/view/",
        arrete_visible_by_user(PrintArreteView.as_view()),
        name="arrete-view",
    ),
    path(
        "arrete/<int:arrete_id>/delete/",
        delete_arrete_view,
        name="delete-arrete",
    ),
    # Arretes signés
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
        "arrete-signe/<int:arrete_signe_id>/view/",
        view_arrete_signe,
        name="arrete-signe-view",
    ),
    path(
        "arrete-signe/<int:arrete_signe_id>/delete/",
        delete_arrete_signe_view,
        name="delete-arrete-signe",
    ),
    # Modèles d'arrêtés
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
    path(
        "modeles/modifier/<str:modele_arrete_id>/",
        UpdateModeleArrete.as_view(),
        name="modele-arrete-modifier",
    ),
    path(
        "modeles/dupliquer/<str:modele_arrete_id>/",
        DuplicateModeleArrete.as_view(),
        name="modele-arrete-dupliquer",
    ),
    path(
        "modele/<str:modele_arrete_id>/",
        delete_modele_arrete_view,
        name="delete-modele-arrete",
    ),
]

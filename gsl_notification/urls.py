from django.urls import path

from gsl_notification.views.views import (
    change_arrete_view,
    create_arrete_signe_view,
    create_arrete_view,
    download_arrete,
    download_arrete_signe,
    get_arrete_view,
)

urlpatterns = [
    path(
        "<int:programmation_projet_id>/arrete-signe/",
        get_arrete_view,
        name="get-arrete",
    ),
    path(
        "<int:programmation_projet_id>/creer-arrete/",
        create_arrete_view,
        name="create-arrete",
    ),
    path(
        "<int:programmation_projet_id>/modifier-arrete/",
        change_arrete_view,
        name="modifier-arrete",
    ),
    path(
        "<int:programmation_projet_id>/creer-arrete-signe/",
        create_arrete_signe_view,
        name="create-arrete-signe",
    ),
    path(
        "arrete/<int:arrete_id>/download/",
        download_arrete,
        name="arrete-download",
    ),
    path(
        "arrete-signe/<int:arrete_signe_id>/download/",
        download_arrete_signe,
        name="arrete-signe-download",
    ),
]

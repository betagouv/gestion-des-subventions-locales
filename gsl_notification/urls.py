from django.urls import path

from gsl_notification.views.views import (
    create_arrete_view,
    download_arrete_signe,
    get_arrete_view,
)

urlpatterns = [
    path(
        "<int:programmation_projet_id>/creer-arrete/",
        create_arrete_view,
        name="create-arrete",
    ),
    path(
        "<int:programmation_projet_id>/arrete-signe/",
        get_arrete_view,
        name="get-arrete",
    ),
    path(
        "arrete/<int:arrete_signe_id>/download/",
        download_arrete_signe,
        name="arrete-signe-download",
    ),
]

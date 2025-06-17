from django.urls import path

from gsl_notification.views import create_arrete_view, get_arrete_view

urlpatterns = [
    path(
        "<int:programmation_projet_id>/creer-arrete/",
        create_arrete_view,  # TODO create user rights
        name="create-arrete",
    ),
    path(
        "<int:programmation_projet_id>/arrete-signe/",
        get_arrete_view,  # TODO create user rights
        name="get-arrete",
    ),
]

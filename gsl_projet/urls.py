from django.urls import path

from . import views

urlpatterns = [
    path(
        "voir/<int:projet_id>/",
        views.get_projet,
        name="get-projet",
    ),
    path("liste", views.ProjetListView.as_view(), name="list"),
]

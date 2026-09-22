from django.urls import path

from .views import ProgrammationListView

urlpatterns = [
    path(
        "",
        ProgrammationListView.as_view(),
        name="programmation-projet-list",
    ),
    path(
        "<str:dotation>/",
        ProgrammationListView.as_view(),
        name="programmation-projet-list-dotation",
    ),
]

from django.urls import path

from . import views
from .views import DossierSansPieceUpdateView

urlpatterns = [
    path(
        "demarche/<int:demarche_ds_number>/json/",
        views.view_demarche_json,
        name="view-demarche-json",
    ),
    path(
        "dossier/<int:dossier_ds_number>/json/",
        views.view_dossier_json,
        name="view-dossier-json",
    ),
    path(
        "dossier/<int:dossier_ds_number>/refresh/",
        views.RefreshOneDossierView.as_view(),
        name="refresh-one-dossier",
    ),
    path(
        "dossier/<int:pk>/renseigner/",
        DossierSansPieceUpdateView.as_view(),
        name="dossier-sans-piece-update",
    ),
]

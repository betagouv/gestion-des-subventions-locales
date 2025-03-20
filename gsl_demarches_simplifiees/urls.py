from django.urls import path

from . import views

urlpatterns = [
    path(
        "ajouter-des-demarches/",
        views.get_ds_demarches_from_numbers,
        name="add-demarches",
    ),
    path(
        "ajouter-des-demarches-post/",
        views.post_get_ds_demarches_from_numbers,
        name="post-add-demarches",
    ),
    path(
        "statut-ds/",
        views.get_celery_task_results,
        name="task-results",
    ),
    path(
        "liste-demarches/",
        views.DemarcheListView.as_view(),
        name="liste-demarches",
    ),
    path(
        "demarche/<int:demarche_ds_number>/mapping/",
        views.get_demarche_mapping,
        name="get-demarche-mapping",
    ),
    path(
        "demarche/fetch-dossiers/",
        views.fetch_demarche_dossiers,
        name="fetch-demarche-dossiers",
    ),
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
]

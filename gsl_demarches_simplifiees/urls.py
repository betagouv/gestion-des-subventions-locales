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
]

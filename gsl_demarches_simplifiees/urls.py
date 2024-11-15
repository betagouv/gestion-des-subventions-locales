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
]

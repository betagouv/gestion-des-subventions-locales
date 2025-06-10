from django.urls import path

from . import views

urlpatterns = [
    path(
        "nouvel-arrete/",
        views.create_arrete,
        name="create-arrete",
    ),
    path("export-pdf/", views.export_pdf, name="export_pdf"),
]

"""gsl URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/

"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("gsl_oidc.urls")),
    path("", include("gsl_pages.urls")),
    path(
        "ds/",
        include(("gsl_demarches_simplifiees.urls", "gsl_demarches_simplifiees"), "ds"),
    ),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("projets/", include(("gsl_projet.urls", "gsl_projet"), "projet")),
    path(
        "programmation/",
        include(("gsl_programmation.urls", "gsl_programmation"), "programmation"),
    ),
]

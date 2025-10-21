"""gsl URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/

"""

from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from gsl import settings


def no_perimeter_view(request):
    return render(request, "no_perimetre.html")


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
        "simulation/",
        include(("gsl_simulation.urls", "gsl_simulation"), "simulation"),
    ),
    path(
        "programmation/",
        include(("gsl_programmation.urls", "gsl_programmation"), "programmation"),
    ),
    path(
        "notification/",
        include(("gsl_notification.urls", "gsl_notification"), "notification"),
    ),
    path("sans-perimetre/", no_perimeter_view, name="no_perimeter"),
]

if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += debug_toolbar_urls()

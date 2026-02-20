"""gsl URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/

"""

from django.contrib import admin
from django.urls import include, path

from gsl import settings

admin.site.site_header = "Back-office Turgot - " + settings.ENV
admin.site.index_title = "Back-office Turgot - " + settings.ENV
admin.site.site_title = "Back-office Turgot - " + settings.ENV

# Django's default handlers convert exception to string - we need these minimal
# handlers to pass the exception object so templates can duck type user_message
handler404 = "gsl_pages.views.custom_404_view"
handler403 = "gsl_pages.views.custom_403_view"
handler500 = "gsl_pages.views.custom_500_view"

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
]

if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += debug_toolbar_urls()

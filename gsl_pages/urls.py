from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("", views.index_view, name="index"),
    path("accessibilite/", views.accessibility_view, name="accessibilite"),
    path(
        "sans-perimetre/",
        TemplateView.as_view(template_name="gsl_pages/no_perimetre.html"),
        name="no-perimeter",
    ),
    path(
        "aide-et-contact/",
        TemplateView.as_view(template_name="gsl_pages/user_help.html"),
        name="user-help-and-contact",
    ),
]

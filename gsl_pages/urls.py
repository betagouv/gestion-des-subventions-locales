from django.urls import path

from . import views

urlpatterns = [
    path("", views.index_view, name="index"),
    path("accessibilite/", views.accessibility_view, name="accessibilite"),
    path("sans-perimetre/", views.no_perimeter_view, name="no-perimeter"),
]

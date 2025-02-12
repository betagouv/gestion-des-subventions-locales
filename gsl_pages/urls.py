from django.urls import path

from . import views

urlpatterns = [
    path("", views.index_view, name="index"),
    path("accessibilite/", views.accessibility_view, name="accessibilite"),
    path(
        "fonctionnalites-a-venir/", views.coming_features_view, name="coming-features"
    ),
]

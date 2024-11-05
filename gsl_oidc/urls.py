from django.urls import include, path

urlpatterns = [
    path("comptes/", include("django.contrib.auth.urls")),
]

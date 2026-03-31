from django.urls import URLPattern, include, path

from gsl_oidc.views import LoginPageView

urlpatterns: list[URLPattern] = [
    path("comptes/login/", LoginPageView.as_view(), name="login"),
    path("oidc/", include("mozilla_django_oidc.urls")),
]

from django.contrib.auth.decorators import login_not_required
from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("otp/setup/", views.OTPSetupView.as_view(), name="otp-setup"),
    path("otp/verify/", views.OTPVerifyView.as_view(), name="otp-verify"),
    path(
        "mentions-legales/",
        login_not_required(
            TemplateView.as_view(template_name="gsl_core/mentions_legales.html")
        ),
        name="mentions-legales",
    ),
    path(
        "donnees-personnelles/",
        login_not_required(
            TemplateView.as_view(template_name="gsl_core/donnees_personnelles.html")
        ),
        name="donnees-personnelles",
    ),
]

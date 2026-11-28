from django.contrib.auth.decorators import login_not_required
from django.urls import path
from django.views.generic import TemplateView

from . import views
from .bulk_actions import bulk_action_wizard
from .campagne import ChangeCampagneView

urlpatterns = [
    path(
        "actions-en-masse/<str:dotation>/<str:action>/",
        bulk_action_wizard,
        name="bulk-action",
    ),
    path(
        "campagne/<int:campagne>/",
        ChangeCampagneView.as_view(),
        name="changer-campagne",
    ),
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

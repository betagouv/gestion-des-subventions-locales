from django.urls import path

from . import views

urlpatterns = [
    path("otp/setup/", views.OTPSetupView.as_view(), name="otp-setup"),
    path("otp/verify/", views.OTPVerifyView.as_view(), name="otp-verify"),
]

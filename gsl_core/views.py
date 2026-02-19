import io

import segno
from django.conf import settings
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice


def _generate_qr_svg(device):
    uri = device.config_url
    qr = segno.make(uri)
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", xmldecl=False, svgns=False, scale=4)
    return buffer.getvalue().decode()


class OTPSetupView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("/")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        device = self._get_or_create_device(request.user)
        qr_svg = _generate_qr_svg(device)
        issuer = getattr(settings, "OTP_TOTP_ISSUER", "Turgot")
        return render(
            request,
            "gsl_core/otp_setup.html",
            {
                "qr_svg": qr_svg,
                "issuer": issuer,
                "secret": device.key,
                "error": None,
            },
        )

    def post(self, request):
        device = self._get_or_create_device(request.user)
        token = request.POST.get("token", "").strip()
        if device.verify_token(token):
            device.confirmed = True
            device.save()
            otp_login(request, device)
            return redirect("/")

        qr_svg = _generate_qr_svg(device)
        issuer = getattr(settings, "OTP_TOTP_ISSUER", "Turgot")
        return render(
            request,
            "gsl_core/otp_setup.html",
            {
                "qr_svg": qr_svg,
                "issuer": issuer,
                "secret": device.key,
                "error": "Code invalide. Veuillez réessayer.",
            },
        )

    def _get_or_create_device(self, user):
        device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
        if not device:
            device = TOTPDevice.objects.create(
                user=user,
                name=f"Turgot ({user.email})",
                confirmed=False,
            )
        return device


class OTPVerifyView(View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("/")
        return super().dispatch(request, *args, **kwargs)

    def _get_next_url(self, request):
        next_url = request.GET.get("next", request.POST.get("next", "/"))
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}
        ):
            return "/"
        return next_url

    def get(self, request):
        return render(
            request,
            "gsl_core/otp_verify.html",
            {
                "error": None,
                "next": self._get_next_url(request),
            },
        )

    def post(self, request):
        next_url = self._get_next_url(request)
        token = request.POST.get("token", "").strip()
        device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
        if device and device.verify_token(token):
            otp_login(request, device)
            return redirect(next_url)

        return render(
            request,
            "gsl_core/otp_verify.html",
            {
                "error": "Code invalide. Veuillez réessayer.",
                "next": next_url,
            },
        )

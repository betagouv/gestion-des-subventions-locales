from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class OTPVerificationMiddleware:
    """
    Middleware enforcing TOTP verification for staff users.

    - Non-authenticated or non-staff users: passes through (zero overhead).
    - Staff with a verified OTP session: passes through.
    - Staff without any TOTP device: redirects to /otp/setup/.
    - Staff with a confirmed device but unverified session: redirects to /otp/verify/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.OTP_ENABLED:
            return self.get_response(request)

        user = request.user

        if not user.is_authenticated or not user.is_staff:
            return self.get_response(request)

        exempt_prefixes = ["/otp/", "/comptes/", "/oidc/"]
        for prefix in exempt_prefixes:
            if request.path.startswith(prefix):
                return self.get_response(request)

        if request.path in (reverse("login"), reverse("logout")):
            return self.get_response(request)

        if user.is_verified():
            return self.get_response(request)

        from django_otp.plugins.otp_totp.models import TOTPDevice

        has_confirmed_device = TOTPDevice.objects.filter(
            user=user, confirmed=True
        ).exists()

        if has_confirmed_device:
            return redirect(
                f"{reverse('otp-verify')}?{urlencode({'next': request.path})}"
            )

        return redirect("otp-setup")


class CheckPerimeterMiddleware:
    """
    Middleware pour vérifier que l'utilisateur connecté a un périmètre associé.
    Sinon, redirige vers une page spécifique.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        excluded_paths = [
            reverse("login"),
            reverse("logout"),
            reverse("no-perimeter"),
        ]
        excluded_beginning_paths = ["/admin/", "/oidc/", "/__debug__/", "/otp/"]
        admin_allowed_paths = ["/ds/"]

        if user.is_staff:
            excluded_beginning_paths.extend(admin_allowed_paths)

        for path in excluded_beginning_paths:
            if request.path.startswith(path):
                return self.get_response(request)

        if user.is_authenticated:
            has_perimeter = user.perimetre
            if not has_perimeter and request.path not in excluded_paths:
                return redirect("no-perimeter")

        response = self.get_response(request)
        return response

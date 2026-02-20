from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse


class AdminIPWhitelistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            ip = self._get_client_ip(request)
            if ip not in settings.ADMIN_ALLOWED_IPS:
                return HttpResponseForbidden()
        return self.get_response(request)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")


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
        excluded_beginning_paths = ["/admin/", "/oidc/", "/__debug__/"]
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

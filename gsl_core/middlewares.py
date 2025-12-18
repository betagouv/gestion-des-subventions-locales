from django.shortcuts import redirect
from django.urls import reverse


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

from django.contrib.auth.middleware import (
    LoginRequiredMiddleware as OriginalLoginRequiredMiddleware,
)


class LoginRequiredMiddleware(OriginalLoginRequiredMiddleware):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_authenticated:
            return None

        if not getattr(view_func, "login_required", True):
            return None

        # allow OIDC views
        if request.path in (
            "/oidc/authenticate/",
            "/oidc/callback/",
        ):
            return None

        return self.handle_no_permission(request, view_func)

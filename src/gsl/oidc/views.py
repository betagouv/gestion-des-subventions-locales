from django.contrib.auth.decorators import login_not_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView


@method_decorator(login_not_required, name="dispatch")
class LoginPageView(TemplateView):
    template_name = "gsl_oidc/login.html"

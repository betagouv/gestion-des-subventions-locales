from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect, render
from django.urls import reverse


@login_not_required
def index_view(request):
    return redirect(
        reverse(
            "projet:list",
        )
    )


@login_not_required
def accessibility_view(request):
    return render(
        request,
        "gsl_pages/accessibilite.html",
        {"title": "Déclaration d’accessibilité"},
    )


@login_not_required
def custom_404_view(request, exception):
    """Pass exception object (not string) to template for duck typing."""
    return render(request, "404.html", {"exception": exception}, status=404)


@login_not_required
def custom_403_view(request, exception):
    """Pass exception object (not string) to template for duck typing."""
    return render(request, "403.html", {"exception": exception}, status=403)


@login_not_required
def custom_500_view(request):
    """Render 500 with request context so {% url %}, {% static %} and DSFR context processors work."""
    return render(request, "500.html", status=500)

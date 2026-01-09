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


def coming_features_view(request):
    return render(
        request,
        "gsl_pages/coming_features.html",
        {"title": "Fonctionnalités à venir"},
    )


def no_perimeter_view(request):
    return render(request, "gsl_pages/no_perimetre.html")


@login_not_required
def custom_404_view(request, exception):
    """Pass exception object (not string) to template for duck typing."""
    return render(request, "404.html", {"exception": exception}, status=404)


@login_not_required
def custom_403_view(request, exception):
    """Pass exception object (not string) to template for duck typing."""
    return render(request, "403.html", {"exception": exception}, status=403)

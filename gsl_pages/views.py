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
def coming_features_view(request):
    return render(
        request,
        "gsl_pages/coming_features.html",
        {"title": "Fonctionnalités à venir"},
    )

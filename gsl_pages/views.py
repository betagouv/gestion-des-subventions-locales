from django.contrib.auth.decorators import login_not_required
from django.shortcuts import render


@login_not_required
def index_view(request):
    return render(
        request, "gsl_pages/index.html", {"title": "Gestion des subventions locales"}
    )


@login_not_required
def accessibility_view(request):
    return render(
        request,
        "gsl_pages/accessibilite.html",
        {"title": "Déclaration d’accessibilité"},
    )

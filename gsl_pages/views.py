from django.shortcuts import render


def index_view(request):
    return render(request, "gsl_pages/index.html", {})


def accessibility_view(request):
    return render(request, "gsl_pages/accessibilite.html", {})

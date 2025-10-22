from django.shortcuts import render


def no_perimeter_view(request):
    return render(request, "no_perimetre.html")

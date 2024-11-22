from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Projet


@require_GET
def get_projet(request, projet_id):
    projet = get_object_or_404(Projet, id=projet_id)
    context = {
        "title": f"Projet {projet}",
        "projet": projet,
        "dossier": projet.dossier_ds,
        "breadcrumb_dict": {
            "links": [{"url": "@todo", "title": "Liste des projets"}],
            "current": f"Projet {projet}",
        },
    }
    return render(request, "gsl_projet/projet.html", context)

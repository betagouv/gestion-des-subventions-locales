from django.http import Http404
from django.shortcuts import get_object_or_404

from gsl_notification.models import ArreteSigne
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.models import Projet

## decorators (to move ??)


def programmation_projet_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        programmation_projet = get_object_or_404(
            ProgrammationProjet, id=kwargs["programmation_projet_id"]
        )
        projet = programmation_projet.projet
        is_projet_visible_by_user = (
            Projet.objects.for_user(user).filter(id=projet.id).exists()
        )
        if not is_projet_visible_by_user:
            raise Http404("No %s matches the given query." % Projet._meta.object_name)

        return func(*args, **kwargs)

    return wrapper


def arrete_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        arrete = get_object_or_404(ArreteSigne, id=kwargs["arrete_signe_id"])
        projet = arrete.programmation_projet.projet
        is_projet_visible_by_user = (
            Projet.objects.for_user(user).filter(id=projet.id).exists()
        )
        if not is_projet_visible_by_user:
            raise Http404("No %s matches the given query." % Projet._meta.object_name)

        return func(*args, **kwargs)

    return wrapper

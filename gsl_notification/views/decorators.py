from django.http import Http404
from django.shortcuts import get_object_or_404

from gsl_notification.utils import (
    get_document_class,
    get_modele_class,
    get_modele_perimetres,
    get_uploaded_document_class,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.models import Projet


def _visible_by_user(model, lookup_kwarg, obj_to_projet):
    def decorator(func):
        def wrapper(*args, **kwargs):
            user = args[0].user
            if user.is_staff:
                return func(*args, **kwargs)
            obj = get_object_or_404(model, id=kwargs[lookup_kwarg])
            projet = obj_to_projet(obj)
            is_projet_visible_by_user = (
                Projet.objects.for_user(user).filter(id=projet.id).exists()
            )
            if not is_projet_visible_by_user:
                raise Http404(
                    "No %s matches the given query." % Projet._meta.object_name
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


programmation_projet_visible_by_user = _visible_by_user(
    ProgrammationProjet,
    "programmation_projet_id",
    lambda obj: obj.projet,
)


def modele_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)
        _class = get_modele_class(kwargs["modele_type"])
        modele = get_object_or_404(_class, id=kwargs["modele_id"])
        dotation = modele.dotation
        visible_perimetres_for_user = get_modele_perimetres(dotation, user.perimetre)
        if modele.perimetre not in visible_perimetres_for_user:
            raise Http404("No %s matches the given query." % Projet._meta.object_name)
        return func(*args, **kwargs)

    return wrapper


def document_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)
        obj_class = get_document_class(kwargs["document_type"])
        obj = get_object_or_404(obj_class, id=kwargs["document_id"])
        projet = obj.programmation_projet.projet
        is_projet_visible_by_user = (
            Projet.objects.for_user(user).filter(id=projet.id).exists()
        )
        if not is_projet_visible_by_user:
            raise Http404("No %s matches the given query." % Projet._meta.object_name)
        return func(*args, **kwargs)

    return wrapper


def uploaded_document_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)
        obj_class = get_uploaded_document_class(kwargs["document_type"])
        obj = get_object_or_404(obj_class, id=kwargs["document_id"])
        projet = obj.programmation_projet.projet
        is_projet_visible_by_user = (
            Projet.objects.for_user(user).filter(id=projet.id).exists()
        )
        if not is_projet_visible_by_user:
            raise Http404("No %s matches the given query." % Projet._meta.object_name)
        return func(*args, **kwargs)

    return wrapper

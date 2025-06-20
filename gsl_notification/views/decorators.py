from django.http import Http404
from django.shortcuts import get_object_or_404

from gsl_notification.models import Arrete, ArreteSigne
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

arrete_visible_by_user = _visible_by_user(
    Arrete,
    "arrete_id",
    lambda obj: obj.programmation_projet.projet,
)

arrete_signe_visible_by_user = _visible_by_user(
    ArreteSigne,
    "arrete_signe_id",
    lambda obj: obj.programmation_projet.projet,
)

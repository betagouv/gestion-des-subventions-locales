from django.shortcuts import get_object_or_404

from gsl_core.exceptions import Http404
from gsl_notification.utils import (
    get_modele_class,
    get_modele_perimetres,
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
            raise Http404("%s non trouvé." % _class._meta.object_name)
        return func(*args, **kwargs)

    return wrapper

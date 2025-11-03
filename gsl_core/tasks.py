import logging
from typing import List

from celery import shared_task
from django.db.models import OuterRef, Subquery

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.models import Profile

logger = logging.getLogger(__name__)


@shared_task
def associate_or_update_ds_profile_to_users(user_ids: List[int]):
    users = Collegue.objects.filter(pk__in=user_ids)
    logger.info("Association de profil DS avec les utilisateurs : début")

    user_without_email_count = users.filter(email="").count()
    if user_without_email_count > 0:
        logger.info(f"{user_without_email_count} utilisateurs n'ont pas d'adresse mail")

    users.exclude(email=None).update(
        ds_profile=Subquery(
            Profile.objects.filter(ds_email=OuterRef("email")).values("pk")[:1]
        )
    )

    emails_of_user_without_profile = set(
        users.exclude(email=None)
        .filter(ds_profile__isnull=True)
        .values_list("email", flat=True)
    )

    logger.info("Association de profil DS avec les utilisateurs : fin")
    if len(emails_of_user_without_profile) > 0:
        logger.info(
            "Des emails n'ont pas été trouvés dans les groupes instructeurs des démarches",
            extra={"emails": ", ".join(emails_of_user_without_profile)},
        )

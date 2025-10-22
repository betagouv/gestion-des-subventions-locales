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

    user_emails = set(users.exclude(email="").values_list("email", flat=True))

    users.exclude(email=None).update(
        ds_profile=Subquery(
            Profile.objects.filter(ds_email=OuterRef("email")).values("pk")[:1]
        )
    )

    logger.info("Association de profil DS avec les utilisateurs : fin")
    if len(user_emails) > 0:
        logger.info(
            f"Ces emails n'ont pas été trouvés dans les groupes instructeurs des démarches : {','.join(user_emails)}"
        )

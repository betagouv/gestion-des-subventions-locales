import logging
from typing import List

from celery import shared_task

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
    ds_profiles = Profile.objects.filter(ds_email__in=user_emails)

    for user in users:
        ds_profile = ds_profiles.filter(ds_email=user.email).first()
        if ds_profile:
            users.filter(email=user.email).update(ds_profile=ds_profile)
            user_emails.remove(user.email)

    logger.info("Association de profil DS avec les utilisateurs : fin")
    if len(user_emails) > 0:
        logger.info(
            f"Ces emails n'ont pas été trouvés dans les groupes instructeurs des démarches : {','.join(user_emails)}"
        )

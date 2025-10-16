import logging
from typing import List

from celery import shared_task

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.models import Demarche

logger = logging.getLogger(__name__)


@shared_task
def associate_or_update_ds_id_to_users(user_ids: List[int]):
    users = Collegue.objects.filter(pk__in=user_ids)
    logger.info("Association d'id DS avec les utilisateurs : début")

    user_without_email_count = users.filter(email="").count()
    if user_without_email_count > 0:
        logger.info(f"{user_without_email_count} utilisateurs n'ont pas d'adresse mail")

    user_emails = set(users.exclude(email="").values_list("email", flat=True))
    demarches = Demarche.objects.all()

    for demarche in demarches:
        instructeurs_groups = demarche.raw_ds_data["groupeInstructeurs"]
        for instructeurs_group in instructeurs_groups:
            for instructeur in instructeurs_group["instructeurs"]:
                instructeur_email = instructeur["email"]
                if instructeur_email in user_emails:
                    users.filter(email=instructeur_email).update(
                        ds_id=instructeur["id"]
                    )
                    user_emails.remove(instructeur_email)

    logger.info("Association d'id DS avec les utilisateurs : fin")
    if len(user_emails) > 0:
        logger.info(
            f"Ces emails n'ont pas été trouvés dans les groupes instructeurs des démarches : {','.join(user_emails)}"
        )

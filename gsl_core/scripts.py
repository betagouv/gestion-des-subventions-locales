import logging

from gsl_core.models import Collegue, Perimetre

logger = logging.getLogger(__name__)


def create_user(email, first_name, last_name, department_number, password):
    user = Collegue.objects.create_user(
        username=email,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )

    try:
        perimetre = Perimetre.objects.get(departement__insee_code=department_number)
        user.perimetre = perimetre
    except Perimetre.DoesNotExist:
        logger.warning(
            "No perimetre found for department, no perimeter will be set",
            extra={"department_number": department_number},
        )

    user.save()

    logger.info("User created", extra={"email": user.email})


def create_user_with_password_generator(
    email, first_name, last_name, department_number, generate_password
):
    password = generate_password(department_number)
    logger.info(f"Generated password: {password}")
    create_user(email, first_name, last_name, department_number, password)

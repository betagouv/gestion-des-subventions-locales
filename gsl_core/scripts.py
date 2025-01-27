from gsl_core.models import Collegue, Perimetre


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
        print(
            f"No perimetre found for department {department_number}, no perimeter will be set"
        )

    user.save()

    print(f"User created: {user.email} with password: {password}")


def create_user_with_password_generator(
    email, first_name, last_name, department_number, generate_password
):
    password = generate_password(department_number)
    create_user(email, first_name, last_name, department_number, password)

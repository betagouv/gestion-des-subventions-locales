from django.core.management.base import BaseCommand

from gsl_core.scripts import create_user


class Command(BaseCommand):
    """
    python manage.py create_gsl_user test@test.com test test 75 password_test
    """

    help = "Create a user from an email, first name, last name, department number and password"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)
        parser.add_argument("first_name", type=str)
        parser.add_argument("last_name", type=str)
        parser.add_argument("department_number", type=str)
        parser.add_argument("password", type=str)

    def handle(self, *args, **kwargs):
        email = kwargs["email"]
        first_name = kwargs["first_name"]
        last_name = kwargs["last_name"]
        department_number = kwargs["department_number"]
        password = kwargs["password"]
        create_user(email, first_name, last_name, department_number, password)

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory


@pytest.mark.django_db
def test_create_collegue():
    assert Collegue.objects.count() == 0
    c = Collegue.objects.create(username="hubert.lingot@example.net")
    assert Collegue.objects.count() == 1
    assert c.username == "hubert.lingot@example.net"


@pytest.mark.django_db
def test_get_or_create_from_email_creates_inactive_collegue_with_unusable_password():
    collegue = Collegue.objects.get_or_create_from_email("Agent.Traitant@Example.Net")

    assert collegue.email == "agent.traitant@example.net"
    assert collegue.username == "agent.traitant@example.net"
    assert collegue.is_active is False
    assert not collegue.has_usable_password()


@pytest.mark.django_db
def test_get_or_create_from_email_returns_existing_collegue_case_insensitively():
    existing = CollegueFactory(email="agent.traitant@example.net")

    collegue = Collegue.objects.get_or_create_from_email("Agent.Traitant@Example.Net")

    assert collegue == existing
    assert Collegue.objects.count() == 1


def test_collegue__str__():
    only_first_name = CollegueFactory.build(first_name="Bernard", username="Azerty")
    assert only_first_name.__str__() == "Bernard"

    only_last_name = CollegueFactory.build(last_name="Morin", username="Azerty")
    assert only_last_name.__str__() == "Morin"

    only_first_name = CollegueFactory.build(first_name="Bernard", last_name="Morin")
    assert only_first_name.__str__() == "Bernard Morin"

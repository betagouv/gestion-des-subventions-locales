import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory


@pytest.mark.django_db
def test_create_collegue():
    assert Collegue.objects.count() == 0
    c = Collegue.objects.create(username="hubert.lingot@example.net")
    assert Collegue.objects.count() == 1
    assert c.username == "hubert.lingot@example.net"


def test_collegue__str__():
    only_first_name = CollegueFactory.build(first_name="Bernard", username="Azerty")
    assert only_first_name.__str__() == "Bernard"

    only_last_name = CollegueFactory.build(last_name="Morin", username="Azerty")
    assert only_last_name.__str__() == "Morin"

    only_first_name = CollegueFactory.build(first_name="Bernard", last_name="Morin")
    assert only_first_name.__str__() == "Bernard Morin"

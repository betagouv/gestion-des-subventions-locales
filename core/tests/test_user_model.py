import pytest

from core.models import Collegue


@pytest.mark.django_db
def test_create_collegue():
    assert Collegue.objects.count() == 0
    c = Collegue.objects.create(username="hubert.lingot@example.net")
    assert Collegue.objects.count() == 1
    assert c.username == "hubert.lingot@example.net"

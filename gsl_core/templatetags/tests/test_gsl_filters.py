from decimal import Decimal

from gsl_core.templatetags.gsl_filters import euro


def test_euro():
    assert euro(1000) == "1\xa0000\xa0€"
    assert euro(1000.23) == "1\xa0000\xa0€"
    assert euro(1000.23, 2) == "1\xa0000,23\xa0€"
    assert euro(Decimal(10000)) == "10\xa0000\xa0€"
    assert euro(None) == "—"
    assert euro(True) == "—"
    assert euro("Pouet") == "—"

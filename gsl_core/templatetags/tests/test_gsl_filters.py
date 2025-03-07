from decimal import Decimal

from gsl_core.templatetags.gsl_filters import (
    create_alert_data,
    euro,
    percent,
    remove_first_word,
)
from gsl_projet.models import Projet
from gsl_projet.views import ProjetListView


def test_euro():
    assert euro(1000) == "1\xa0000\xa0€"
    assert euro(1000.23) == "1\xa0000\xa0€"
    assert euro(1000.23, 2) == "1\xa0000,23\xa0€"
    assert euro(Decimal(10000)) == "10\xa0000\xa0€"
    assert euro(None) == "—"
    assert euro(True) == "—"
    assert euro("Pouet") == "—"


def test_percent():
    assert percent(Decimal("12.34")) == "12\xa0%"
    assert percent(Decimal("12.34"), 2) == "12,34\xa0%"
    assert percent(None) == "— %"
    assert percent("Pouet") == "Pouet"


def test_remove_first_word():
    assert remove_first_word("Hello World") == "World"
    assert remove_first_word("One more test") == "more test"
    assert remove_first_word("Single") == ""

    mapping = ProjetListView.STATE_MAPPINGS
    assert remove_first_word(mapping[Projet.STATUS_ACCEPTED]) == "Accepté"
    assert remove_first_word(mapping[Projet.STATUS_REFUSED]) == "Refusé"
    assert remove_first_word(mapping[Projet.STATUS_DISMISSED]) == "Classé sans suite"
    assert remove_first_word(mapping[Projet.STATUS_PROCESSING]) == "En traitement"


def test_create_alert_data():
    assert create_alert_data(None, "Test description") == {
        "is_collapsible": True,
        "title": "Test description",
    }
    assert create_alert_data("valid", "Test description") == {
        "is_collapsible": True,
        "description": "Test description",
        "title": "Projet accepté",
    }
    assert create_alert_data("cancelled", "Test description") == {
        "is_collapsible": True,
        "description": "Test description",
        "title": "Projet refusé",
    }
    assert create_alert_data("other", "Test description") == {
        "is_collapsible": True,
        "description": "Test description",
    }

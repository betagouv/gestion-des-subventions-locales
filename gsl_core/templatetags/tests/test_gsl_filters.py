from decimal import Decimal

import pytest

from gsl_core.templatetags.gsl_filters import (
    create_alert_data,
    euro,
    format_demandeur_nom,
    percent,
    remove_first_word,
)
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
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
    assert remove_first_word(mapping[PROJET_STATUS_ACCEPTED]) == "Accepté"
    assert remove_first_word(mapping[PROJET_STATUS_REFUSED]) == "Refusé"
    assert remove_first_word(mapping[PROJET_STATUS_DISMISSED]) == "Classé sans suite"
    assert remove_first_word(mapping[PROJET_STATUS_PROCESSING]) == "En traitement"


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


@pytest.mark.parametrize(
    "input,expected",
    (
        (
            "CTE DE COMMUNES DE LA PLAINE DE L'AIN",
            "CTE de Communes de la Plaine de l'Ain",
        ),
        ("MAISON DE RETRAITE LA MONTAGNE", "Maison de Retraite la Montagne"),
        ("COMMUNE DE FAREINS", "Commune de Fareins"),
        ("COMMUNE DE SAINT-BERNARD", "Commune de Saint-Bernard"),
        ("CA DU BASSIN DE BOURG-EN-BRESSE", "CA du Bassin de Bourg-en-Bresse"),
        ("COMMUNE DE SAINT-MARTIN-DE-BAVEL", "Commune de Saint-Martin-de-Bavel"),
        ("CC BRESSE ET SAONE", "CC Bresse et Saone"),
        ("COMMUNE DE MONTMERLE SUR SAONE", "Commune de Montmerle sur Saone"),
        ("COMMUNE DE CHEVROUX", "Commune de Chevroux"),
        ("COMMUNE DE DIVONNE-LES-BAINS", "Commune de Divonne-les-Bains"),
        ("COMMUNE DES NEYROLLES", "Commune des Neyrolles"),
        ("COMMUNE DE TOUSSIEUX", "Commune de Toussieux"),
        ("COMMUNE DE NEUVILLE LES DAMES", "Commune de Neuville les Dames"),
        ("COMMUNE DE MANZIAT", "Commune de Manziat"),
        ("COMMUNE DE SAINTE EUPHEMIE", "Commune de Sainte Euphemie"),
        ("COMMUNE DE BENY", "Commune de Beny"),
        (
            "COMMUNE DE SAINT-ETIENNE-SUR-CHALARONNE",
            "Commune de Saint-Etienne-sur-Chalaronne",
        ),
        ("COMMUNE DE TREVOUX", "Commune de Trevoux"),
        ("CC BUGEY SUD", "CC Bugey Sud"),
        ("COMMUNE DE THOISSEY", "Commune de Thoissey"),
        ("COMMUNE D ARGIS", "Commune d'Argis"),
        ("COMMUNE DOUARD A MENEZ", "Commune Douard a Menez"),
    ),
)
def test_format_demandeur_nom(input, expected):
    assert format_demandeur_nom(input) == expected

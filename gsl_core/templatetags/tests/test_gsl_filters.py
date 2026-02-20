from decimal import Decimal

import pytest

from gsl_core.templatetags.gsl_filters import (
    create_alert_data,
    euro,
    euro_value,
    format_demandeur_nom,
    percent,
    percent_value,
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
    assert percent(Decimal("12.34")) == "12 %"
    assert percent(Decimal("12.34"), 2) == "12,34 %"
    assert percent(None) == "— %"
    assert percent("Pouet") == "Pouet"


def test_euro_value():
    assert euro_value(1000) == "1 000"
    assert euro_value(1000.23) == "1 000"
    assert euro_value(1000.23, 2) == "1 000,23"
    assert euro_value(Decimal(10000)) == "10 000"
    assert euro_value(None) == "—"
    assert euro_value(True) == "—"
    assert euro_value("Pouet") == "—"


def test_percent_value():
    assert percent_value(Decimal("12.34")) == "12"
    assert percent_value(Decimal("12.34"), 2) == "12,34"
    assert percent_value(None) == "—"
    assert percent_value("") == "—"
    assert percent_value("Pouet") == "Pouet"


def test_remove_first_word():
    assert remove_first_word("Hello World") == "World"
    assert remove_first_word("One more test") == "more test"
    assert remove_first_word("Single") == ""

    mapping = ProjetListView.STATE_MAPPINGS
    assert remove_first_word(mapping[PROJET_STATUS_ACCEPTED]) == "Accepté"
    assert remove_first_word(mapping[PROJET_STATUS_REFUSED]) == "Refusé"
    assert remove_first_word(mapping[PROJET_STATUS_DISMISSED]) == "Classé sans suite"
    assert remove_first_word(mapping[PROJET_STATUS_PROCESSING]) == "En traitement"


@pytest.mark.parametrize(
    "extra_tags, title_expected",
    (
        ("valid", "Projet accepté"),
        ("cancelled", "Projet refusé"),
        ("provisionally_accepted", "Dotation acceptée provisoirement"),
        ("provisionally_refused", "Dotation refusée provisoirement"),
        ("dismissed", "Projet classé sans suite"),
        ("draft", "Projet en traitement"),
        ("projet_note_deletion", "Suppression de la note"),
        ("delete_modele_arrete", "Modèle supprimé"),
        ("info", None),
        ("alert", None),
        ("other", None),
        (None, None),
    ),
)
def test_create_alert_data_title(extra_tags, title_expected):
    message_text = "Test description"
    message = type("Message", (object,), {"level_tag": "success"})()
    message.message = message_text
    message.extra_tags = extra_tags

    data = create_alert_data(message)

    assert data["is_collapsible"] is True
    assert data["description"] == message_text

    if title_expected:
        assert data["title"] == title_expected
    else:
        assert "title" not in data


@pytest.mark.parametrize(
    "extra_tags, class_expected",
    (
        ("valid", "success"),
        ("cancelled", "error"),
        ("provisionally_accepted", "info"),
        ("provisionally_refused", "brown"),
        ("dismissed", "orange"),
        ("draft", "grey"),
        ("projet_note_deletion", "error"),
        ("delete_modele_arrete", "grey"),
        ("alert", None),
        ("error", None),
        ("other", None),
        (None, None),
    ),
)
def test_create_alert_data_class(extra_tags, class_expected):
    message = type(
        "Message", (object,), {"message": "Mon message", "level_tag": "success"}
    )()
    message.extra_tags = extra_tags

    data = create_alert_data(message)

    if class_expected:
        assert data["class"] == class_expected
    else:
        assert "class" not in data


@pytest.mark.parametrize(
    "extra_tags, icon_expected",
    (
        ("valid", None),
        ("cancelled", None),
        ("provisionally_accepted", None),
        ("provisionally_refused", None),
        ("dismissed", None),
        ("draft", None),
        ("projet_note_deletion", None),
        ("delete_modele_arrete", "fr-icon-delete-bin-fill"),
        ("alert", None),
        ("error", None),
        ("other", None),
        (None, None),
    ),
)
def test_create_alert_data_icon(extra_tags, icon_expected):
    message = type(
        "Message", (object,), {"message": "Mon message", "level_tag": "success"}
    )()
    message.extra_tags = extra_tags

    data = create_alert_data(message)

    if icon_expected:
        assert data["icon"] == icon_expected
    else:
        assert "icon" not in data


@pytest.mark.parametrize(
    "level_tag, type_expected",
    (
        ("info", None),
        ("warning", "warning"),
        (
            "success",
            None,
        ),
        ("error", "alert"),
    ),
)
def test_create_alert_data_type(level_tag, type_expected):
    message = type(
        "Message",
        (object,),
        {"message": "Mon message", "level_tag": level_tag, "extra_tags": ""},
    )()

    data = create_alert_data(message)

    if type_expected:
        assert data["type"] == type_expected
    else:
        assert "type" not in data


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

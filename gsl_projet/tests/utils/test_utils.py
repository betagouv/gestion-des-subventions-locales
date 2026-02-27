from decimal import Decimal

import pytest

from gsl_projet.tests.factories import ProjetFactory
from gsl_projet.utils.utils import (
    compute_taux,
    get_comment_cards,
    order_couples_tuple_by_first_value,
)


@pytest.fixture
def choices():
    return (("b", "value1"), ("a", "value2"), ("c", "value3"))


def test_order_couples_tuple_by_first_value(choices):
    ordered_first_values = ["a", "b", "c"]
    expected = [("a", "value2"), ("b", "value1"), ("c", "value3")]
    result = order_couples_tuple_by_first_value(choices, ordered_first_values)
    assert result == expected


def test_order_couples_tuple_by_first_value_reversed(choices):
    ordered_first_values = ["c", "b", "a"]
    expected = [("c", "value3"), ("b", "value1"), ("a", "value2")]
    result = order_couples_tuple_by_first_value(choices, ordered_first_values)
    assert result == expected


def test_order_couples_tuple_by_first_value_missing_values(choices):
    ordered_first_values = ["a", "b"]
    expected = [("a", "value2"), ("b", "value1"), ("c", "value3")]
    result = order_couples_tuple_by_first_value(choices, ordered_first_values)
    assert result == expected


def test_order_couples_tuple_by_first_value_empty_choices():
    choices = ()
    ordered_first_values = ["a", "b", "c"]
    expected = []
    result = order_couples_tuple_by_first_value(choices, ordered_first_values)
    assert result == expected


@pytest.mark.parametrize(
    "numerator, denominator, expected_taux",
    (
        (10_000, 30_000, 33.333),
        (10_000, 0, 0),
        (10_000, 10_000, 100),
        (100_000, 10_000, 1000),  # we accept more than 100%
        (10_000, -3_000, 0),
        (0, 0, 0),
        (Decimal(0), Decimal(0), 0),
        (0, None, 0),
        (None, 0, 0),
        (1_000, None, 0),
        (None, 4_000, 0),
    ),
)
def test_compute_taux(numerator, denominator, expected_taux):
    taux = compute_taux(numerator, denominator)
    assert taux == round(Decimal(expected_taux), 3)


@pytest.mark.django_db
def test_get_comment_cards_returns_three_cards():
    """get_comment_cards retourne 3 cartes avec num, value et form."""
    projet = ProjetFactory(
        comment_1="Com 1",
        comment_2="",
        comment_3="Com 3",
    )
    cards = get_comment_cards(projet)
    assert len(cards) == 3
    assert cards[0]["num"] == "1" and cards[0]["value"] == "Com 1"
    assert cards[1]["num"] == "2" and cards[1]["value"] == ""
    assert cards[2]["num"] == "3" and cards[2]["value"] == "Com 3"
    for card in cards:
        assert "form" in card
        assert card["form"].initial.get("comment_number") == card["num"]

from decimal import Decimal

import pytest

from gsl_projet.utils.utils import (
    compute_taux,
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

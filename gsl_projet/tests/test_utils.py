import pytest

from gsl_projet.utils.utils import (
    order_couples_tuple_by_first_value,
    transform_choices_to_map,
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


def test_transform_choices_to_map(choices):
    expected = {"b": "value1", "a": "value2", "c": "value3"}
    result = transform_choices_to_map(choices)
    assert result == expected


def test_transform_choices_to_map_empty_choices():
    choices = ()
    expected = {}
    result = transform_choices_to_map(choices)
    assert result == expected


def test_transform_choices_to_map_duplicate_keys():
    choices = (("a", "value1"), ("a", "value2"), ("b", "value3"))
    expected = {"a": "value2", "b": "value3"}  # Last key-value pair should overwrite
    result = transform_choices_to_map(choices)
    assert result == expected

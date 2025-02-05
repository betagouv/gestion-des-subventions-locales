import pytest

from gsl_simulation.utils import (
    get_filters_dict_from_params,
    replace_comma_by_dot,
)


@pytest.mark.parametrize(
    "input_str, expected_float",
    [
        ("10 000 ,00", 10000.00),
        ("10 0   0 0 ,00", 10000.00),
        ("0.5670", 0.57),
        ("10 0   0 0 ,5670", 10000.57),
        ("", 0.0),  # Test empty string
        ("invalid", 0.0),  # Test invalid string
    ],
)
def test_replace_comma_by_dot(input_str, expected_float):
    assert replace_comma_by_dot(input_str) == expected_float


@pytest.mark.parametrize(
    "filter_params, expected_result",
    [
        ("key1=value1", {"key1": "value1"}),
        ("key1=value1&key1=value2", {"key1": ["value1", "value2"]}),
        ("key1=value1&key2=value2&key3=", {"key1": "value1", "key2": "value2"}),
        ("", {}),
        ("key1=", {}),
    ],
)
def test_get_filters_dict_from_params(filter_params, expected_result):
    result = get_filters_dict_from_params(filter_params)
    assert result == expected_result

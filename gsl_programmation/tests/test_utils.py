import pytest

from gsl_programmation.utils import replace_comma_by_dot


@pytest.mark.parametrize(
    "input_str, expected_float",
    [
        ("10 000 ,00", 10000.00),
        ("10 0   0 0 ,00", 10000.00),
        ("10 0   0 0 ,5670", 10000.57),
        ("", 0.0),  # Test empty string
        ("invalid", 0.0),  # Test invalid string
    ],
)
def test_replace_comma_by_dot(input_str, expected_float):
    assert replace_comma_by_dot(input_str) == expected_float

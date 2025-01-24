import re
from urllib.parse import parse_qs


def replace_comma_by_dot(value: str | None) -> float | None:
    """
    Convert a string with spaces and commas to a float.
    Example: "10 000 ,00" -> 10000.00
    """
    if value is None:
        return None

    # Remove all spaces
    value = re.sub(r"\s+", "", value)

    # Replace comma with dot
    value = value.replace(",", ".")

    try:
        return round(float(value), 2)
    except ValueError:
        return 0.0


def get_filters_dict_from_params(filter_params):
    return {
        key: value[0] if len(value) == 1 else value
        for key, value in parse_qs(filter_params).items()
    }

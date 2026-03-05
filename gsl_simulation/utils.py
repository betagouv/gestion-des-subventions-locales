import re


def replace_comma_by_dot(value: str | None, decimals: int = 2) -> float | None:
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
        return round(float(value), decimals)
    except ValueError:
        return 0.0

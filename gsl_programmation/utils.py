def replace_comma_by_dot(value: str) -> str:
    if value is None:
        return value
    return value.replace(",", ".")

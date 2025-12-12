from decimal import Decimal, InvalidOperation


def order_couples_tuple_by_first_value(
    choices: tuple[tuple[str, str], ...], ordered_first_values: tuple[str, ...]
):
    order_dict = {status: index for index, status in enumerate(ordered_first_values)}
    return sorted(
        choices,
        key=lambda x: order_dict[x[0]] if x[0] in order_dict else 1,
    )


def transform_choices_to_map(choices: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return {key: value for key, value in choices}


def compute_taux(numerator: float | Decimal, denominator: float | Decimal) -> Decimal:
    try:
        new_taux = round((Decimal(numerator) / Decimal(denominator)) * 100, 3)
        return max(new_taux, Decimal(0))
    except TypeError:
        return Decimal(0)
    except ZeroDivisionError:
        return Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def floatize(value: float | Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)

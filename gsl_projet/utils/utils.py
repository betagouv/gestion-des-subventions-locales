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


def compute_taux(
    numerator: float | Decimal,
    denominator: float | Decimal,
    decimals: int | None = None,
) -> Decimal:
    try:
        if decimals is None:
            taux = Decimal(numerator) / Decimal(denominator) * 100
        else:
            taux = round((Decimal(numerator) / Decimal(denominator)) * 100, decimals)
        return max(taux, Decimal(0))
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


def get_comment_cards(projet):
    """Retourne la liste des cartes commentaires d'arbitrage pour le template."""

    from gsl_projet.forms import ProjetCommentForm

    return [
        {
            "num": "1",
            "value": projet.comment_1,
            "form": ProjetCommentForm(initial={"comment_number": "1"}, instance=projet),
        },
        {
            "num": "2",
            "value": projet.comment_2,
            "form": ProjetCommentForm(initial={"comment_number": "2"}, instance=projet),
        },
        {
            "num": "3",
            "value": projet.comment_3,
            "form": ProjetCommentForm(initial={"comment_number": "3"}, instance=projet),
        },
    ]

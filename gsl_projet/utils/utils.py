# TODO : test


def order_couples_tuple_by_first_value(
    choices: tuple[tuple[str, str]], ordered_first_values: list[str]
):
    order_dict = {status: index for index, status in enumerate(ordered_first_values)}
    return sorted(choices, key=lambda x: order_dict[x[0]])

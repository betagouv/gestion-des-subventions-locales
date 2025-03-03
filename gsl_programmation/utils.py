def is_there_less_or_equal_than_0_009_of_difference(a: float, b: float) -> bool:
    return round(abs(round(a, 4) - round(b, 4)), 4) <= 0.009

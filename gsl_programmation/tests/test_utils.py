from gsl_programmation.utils import is_there_less_or_equal_than_0_009_of_difference


def test_is_there_less_or_equal_than_0_009_of_difference_true():
    assert is_there_less_or_equal_than_0_009_of_difference(1.001, 1.002) is True
    assert is_there_less_or_equal_than_0_009_of_difference(1.0, 1.008) is True
    assert is_there_less_or_equal_than_0_009_of_difference(-1.0, -1.008) is True


def test_is_there_less_or_equal_than_0_009_of_difference_false():
    assert is_there_less_or_equal_than_0_009_of_difference(1.0, 1.01) is False
    assert is_there_less_or_equal_than_0_009_of_difference(1.0, 1.02) is False
    assert is_there_less_or_equal_than_0_009_of_difference(-1.0, -1.02) is False


def test_is_there_less_or_equal_than_0_009_of_difference_edge_cases():
    assert is_there_less_or_equal_than_0_009_of_difference(1.0, 1.009) is True  # 0,009
    assert (
        is_there_less_or_equal_than_0_009_of_difference(1.0, 1.0091) is False
    )  # 0,0091

    assert is_there_less_or_equal_than_0_009_of_difference(1.0, 0.991) is True  # 0,009
    assert (
        is_there_less_or_equal_than_0_009_of_difference(1.0, 0.9909) is False
    )  # 0,0091

    assert (
        is_there_less_or_equal_than_0_009_of_difference(-1.0, -1.009) is True
    )  # 0,009
    assert (
        is_there_less_or_equal_than_0_009_of_difference(-1.0, -1.0091) is False
    )  # 0,0091

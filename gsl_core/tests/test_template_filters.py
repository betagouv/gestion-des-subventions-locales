import pytest

from gsl_core.table_columns import Column
from gsl_core.templatetags.gsl_filters import (
    active_sort_label,
    aria_sort,
    sort_url_param,
)


@pytest.fixture
def sortable_column():
    return Column(key="cout", label="Coût", getter=lambda ctx: "", sort_param="cout")


@pytest.fixture
def non_sortable_column():
    return Column(key="label", label="Label", getter=lambda ctx: "")


@pytest.fixture
def columns(sortable_column):
    return [
        sortable_column,
        Column(
            key="date", label="Date de dépôt", getter=lambda ctx: "", sort_param="date"
        ),
    ]


class TestActiveSortLabel:
    def test_returns_label_for_matching_column(self, columns):
        assert active_sort_label(columns, "cout") == "Coût"

    def test_returns_label_for_descending_order(self, columns):
        assert active_sort_label(columns, "-date") == "Date de dépôt"

    def test_returns_empty_when_no_order(self, columns):
        assert active_sort_label(columns, "") == ""

    def test_returns_empty_when_order_matches_no_column(self, columns):
        assert active_sort_label(columns, "unknown") == ""


class TestSortUrlParam:
    def test_no_current_order_returns_asc(self, sortable_column):
        assert sort_url_param(sortable_column, "") == "cout"

    def test_asc_returns_desc(self, sortable_column):
        assert sort_url_param(sortable_column, "cout") == "-cout"

    def test_desc_returns_empty(self, sortable_column):
        assert sort_url_param(sortable_column, "-cout") == ""

    def test_different_column_sorted_returns_asc(self, sortable_column):
        assert sort_url_param(sortable_column, "date") == "cout"

    def test_non_sortable_column_returns_empty(self, non_sortable_column):
        assert sort_url_param(non_sortable_column, "") == ""


class TestAriaSort:
    def test_ascending(self, sortable_column):
        assert aria_sort(sortable_column, "cout") == "ascending"

    def test_descending(self, sortable_column):
        assert aria_sort(sortable_column, "-cout") == "descending"

    def test_no_sort(self, sortable_column):
        assert aria_sort(sortable_column, "") == "none"

    def test_different_column_sorted(self, sortable_column):
        assert aria_sort(sortable_column, "date") == "none"

    def test_non_sortable_column(self, non_sortable_column):
        assert aria_sort(non_sortable_column, "cout") == "none"

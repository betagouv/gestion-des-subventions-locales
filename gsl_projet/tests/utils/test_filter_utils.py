from unittest.mock import MagicMock

import pytest

from gsl_projet.utils.filter_utils import FilterUtils


@pytest.fixture
def filter_utils():
    # Create a subclass to mock the request object
    class MockFilterUtils(FilterUtils):
        def __init__(self, request):
            self.request = request

        def _get_perimetre(self):
            return MagicMock(entity_name="France")

        def _get_territoire_choices(self):
            return ["Choice 1", "Choice 2"]

        def _get_categorie_detr_choices(self):
            return ["Category 1", "Category 2"]

    return MockFilterUtils


def test_enrich_context_with_filter_utils_no_filters(filter_utils):
    request = MagicMock()
    request.GET.get.side_effect = lambda key, default=None: ""
    request.GET.getlist.side_effect = lambda key: []

    instance = filter_utils(request)
    context = {}
    state_mappings = {"status1": "Status 1", "status2": "Status 2"}

    result = instance.enrich_context_with_filter_utils(context, state_mappings)

    assert result["is_dotation_active"] is False
    assert result["dotation_placeholder"] == "Toutes les dotations"
    assert result["is_status_active"] is False
    assert result["status_placeholder"] == "Tous"
    assert result["is_porteur_active"] is False
    assert result["porteur_placeholder"] == "Tous"
    assert result["is_territoire_active"] is False
    assert result["territoire_placeholder"] == "France"
    assert result["territoire_choices"] == ["Choice 1", "Choice 2"]


def test_enrich_context_with_filter_utils_with_filters(filter_utils):
    request = MagicMock()
    request.GET.get.side_effect = lambda key, default=None: {
        "dotation": "DETR",
        "status": "status1",
        "porteur": "epci",
    }.get(key, "")
    request.GET.getlist.side_effect = lambda key: {
        "dotation": ["DETR", "DSIL"],
        "status": ["status1"],
        "porteur": ["epci"],
    }.get(key, [])

    instance = filter_utils(request)
    context = {}
    state_mappings = {"status1": "Status 1", "status2": "Status 2"}

    result = instance.enrich_context_with_filter_utils(context, state_mappings)

    assert result["is_dotation_active"] is True
    assert result["dotation_placeholder"] == "DETR, DSIL"
    assert result["is_status_active"] is True
    assert result["status_placeholder"] == "Status 1"
    assert result["is_porteur_active"] is True
    assert result["porteur_placeholder"] == "EPCI"
    assert result["is_territoire_active"] is False
    assert result["territoire_placeholder"] == "France"
    assert result["territoire_choices"] == ["Choice 1", "Choice 2"]


@pytest.mark.parametrize(
    "values, expected_placeholder",
    [
        ("", "Toutes les dotations"),
        (None, "Toutes les dotations"),
        ([], "Toutes les dotations"),
        (["DSIL"], "DSIL"),
        (["DETR", "DSIL"], "DETR, DSIL"),
        (["DETR", "DSIL", "DETR_et_DSIL"], "DETR, DSIL, DETR et DSIL"),
    ],
)
def test_get_dotation_placeholder(filter_utils, values, expected_placeholder):
    request = MagicMock()
    request.GET.getlist.return_value = values
    instance = filter_utils(request)

    result = instance._get_dotation_placeholder()

    assert result == expected_placeholder


@pytest.mark.parametrize(
    "values, expected_placeholder",
    [
        ("", "Tous"),
        (None, "Tous"),
        ([], "Tous"),
        (["epci"], "EPCI"),
        (["epci", "communes"], "EPCI, Communes"),
        (["epci", "communes", "autre"], "EPCI, Communes, Autre"),
    ],
)
def test_get_porteur_placeholder(filter_utils, values, expected_placeholder):
    request = MagicMock()
    request.GET.getlist.return_value = values
    instance = filter_utils(request)

    result = instance._get_porteur_placeholder()

    assert result == expected_placeholder


@pytest.mark.parametrize(
    "values, expected_result",
    [
        (["dotation"], True),
        (["status"], False),
        (["porteur"], True),
        (["montant_retenu_min", "montant_retenu_max"], True),
    ],
)
def test_get_is_one_field_active(filter_utils, values, expected_result):
    request = MagicMock()
    request.GET.get.side_effect = lambda key, default=None: {
        "dotation": "DETR",
        "status": "",
        "porteur": "epci",
        "montant_retenu_min": "",
        "montant_retenu_max": "10",
    }.get(key, "")

    instance = filter_utils(request)

    result = instance._get_is_one_field_active(*values)

    assert result == expected_result

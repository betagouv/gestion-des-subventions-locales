from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy

from gsl_simulation.views.mixins import CorrectUserPerimeterRequiredMixin


@pytest.mark.django_db
class TestCorrectUserPerimeterRequiredMixin:
    @patch("gsl_simulation.views.mixins.get_object_or_404")
    @patch(
        "gsl_simulation.views.mixins.EnveloppeService.get_enveloppes_visible_for_a_user"
    )
    def test_test_func_with_valid_user(
        self, mock_get_enveloppes, mock_get_object_or_404, rf
    ):
        mock_user = MagicMock()
        mock_request = rf.get("/some-url/")
        mock_request.user = mock_user
        mock_request.resolver_match = MagicMock()
        mock_request.resolver_match.kwargs = {"pk": 1}

        mock_simulation_projet = MagicMock()
        mock_simulation_projet.enveloppe = "enveloppe_1"
        mock_get_object_or_404.return_value = mock_simulation_projet

        mock_get_enveloppes.return_value = ["enveloppe_1", "enveloppe_2"]

        mixin = CorrectUserPerimeterRequiredMixin()
        mixin.request = mock_request

        assert mixin.test_func() is True

    @patch("gsl_simulation.views.mixins.get_object_or_404")
    @patch(
        "gsl_simulation.views.mixins.EnveloppeService.get_enveloppes_visible_for_a_user"
    )
    def test_test_func_with_invalid_user(
        self, mock_get_enveloppes, mock_get_object_or_404, rf
    ):
        mock_user = MagicMock()
        mock_request = rf.get("/some-url/")
        mock_request.user = mock_user
        mock_request.resolver_match = MagicMock()
        mock_request.resolver_match.kwargs = {"pk": 1}

        mock_simulation_projet = MagicMock()
        mock_simulation_projet.enveloppe = "enveloppe_3"
        mock_get_object_or_404.return_value = mock_simulation_projet

        mock_get_enveloppes.return_value = ["enveloppe_1", "enveloppe_2"]

        mixin = CorrectUserPerimeterRequiredMixin()
        mixin.request = mock_request

        assert mixin.test_func() is False

    def test_handle_no_permission(self):
        mixin = CorrectUserPerimeterRequiredMixin()

        response = mixin.handle_no_permission()
        assert isinstance(response, HttpResponseRedirect)
        assert response.url == reverse_lazy("simulation:simulation-list")

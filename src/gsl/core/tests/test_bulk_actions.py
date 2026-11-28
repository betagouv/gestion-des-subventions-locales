from html import unescape

import pytest
from django.test import override_settings
from django.urls import reverse

from dn.sync.models import Dotation
from gsl.core.tests.factories import ClientWithLoggedUserFactory, CollegueFactory

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=False)
def test_unknown_action_is_not_found():
    client = ClientWithLoggedUserFactory(CollegueFactory())
    response = client.get(
        reverse("bulk-action", args=[Dotation.DETR, "inconnue"]),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 404
    assert "Action inconnue" in unescape(response.content.decode("utf-8"))

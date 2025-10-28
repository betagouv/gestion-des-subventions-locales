import pytest
from django.urls import reverse
from pytest_django.asserts import assertTemplateUsed

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
)


@pytest.mark.parametrize(
    "url_name, template_name",
    (
        ("accessibilite", "gsl_pages/accessibilite.html"),
        ("coming-features", "gsl_pages/coming_features.html"),
        ("no-perimeter", "gsl_pages/no_perimetre.html"),
    ),
)
@pytest.mark.django_db
def test_pages_url(url_name, template_name):
    user = CollegueFactory()
    client = ClientWithLoggedUserFactory(user)
    url = reverse(f"{url_name}")

    response = client.get(url)

    assert response.status_code == 200
    assertTemplateUsed(response, template_name)

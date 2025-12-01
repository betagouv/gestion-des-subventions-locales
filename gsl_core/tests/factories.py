import factory
from django.test import Client, RequestFactory

from ..models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Perimetre,
    Region,
)


class RegionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Region

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("word", locale="fr_FR")


class DepartementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Departement

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("word", locale="fr_FR")
    region = factory.SubFactory(RegionFactory)


class ArrondissementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Arrondissement

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("city", locale="fr_FR")
    departement = factory.SubFactory(DepartementFactory)


class CommuneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Commune

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("city", locale="fr_FR")
    arrondissement = factory.SubFactory(ArrondissementFactory)
    departement = factory.LazyAttribute(lambda obj: obj.arrondissement.departement)


class AdresseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Adresse

    label = factory.Faker("address", locale="fr_FR")
    postal_code = factory.Faker("postcode", locale="fr_FR")
    commune = factory.SubFactory(CommuneFactory)
    street_address = factory.Faker("street_address", locale="fr_FR")


class PerimetreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Perimetre
        django_get_or_create = ("arrondissement", "departement", "region")

    arrondissement = None
    departement = factory.SubFactory(DepartementFactory)
    region = factory.LazyAttribute(lambda obj: obj.departement.region)


class PerimetreDepartementalFactory(PerimetreFactory):
    pass


class PerimetreRegionalFactory(PerimetreFactory):
    departement = None
    region = factory.SubFactory(RegionFactory)


class PerimetreArrondissementFactory(PerimetreFactory):
    arrondissement = factory.SubFactory(ArrondissementFactory)
    departement = factory.LazyAttribute(lambda obj: obj.arrondissement.departement)
    region = factory.LazyAttribute(lambda obj: obj.arrondissement.departement.region)


class CollegueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Collegue

    username = factory.Sequence(lambda n: f"collegue_{n}")
    email = factory.Faker("email")
    is_staff = False
    is_active = True
    perimetre = factory.SubFactory(PerimetreFactory)


class CollegueWithDSProfileFactory(CollegueFactory):
    ds_profile = factory.SubFactory(
        "gsl_demarches_simplifiees.tests.factories.ProfileFactory"
    )


class RequestFactory(RequestFactory):
    user = factory.SubFactory(CollegueFactory)

    def __init__(self, user=user, **kwargs):
        super().__init__(**kwargs)
        self.user = user

    def get(self, path: str, data: dict = None, **extra):
        request = super().get(path, data, **extra)
        request.user = self.user
        return request


class HtmxAwareClient(Client):
    """
    A test client that automatically follows HTMX redirects and page refreshes.

    Handles:
    - HX-Redirect: Follows client-side redirects (like HTTP redirects)
    - HX-Refresh: Performs a full page refresh by GET-ing the current URL
    - HX-Location: Handles client-side navigation with optional swap instructions

    Usage:
        client = HtmxAwareClient()
        response = client.post('/api/endpoint/', data={'key': 'value'})
        # Automatically follows any HX-Redirect, HX-Refresh, or HX-Location headers

        # To disable auto-following for a specific request:
        response = client.post('/api/endpoint/', data={}, follow=False)
    """

    def __init__(self, *args, **kwargs):
        self._follow_htmx = kwargs.pop("follow_htmx", True)
        self._max_redirects = kwargs.pop("max_redirects", 5)
        self._current_url = None  # Track the current URL for HX-Refresh
        super().__init__(*args, **kwargs)

    def _follow_htmx_response(self, response, request_headers):
        """
        Follow HTMX-specific response headers that trigger client-side navigation.

        Args:
            response: The HTTP response to check for HTMX headers
            request_headers: The request headers that triggered the response (for HX-Refresh)

        Returns the final response after following any HTMX redirects/refreshes.
        """
        redirects_followed = 0

        while redirects_followed < self._max_redirects:
            # Check for HX-Redirect header
            if "HX-Redirect" in response:
                redirect_url = response["HX-Redirect"]
                self._current_url = redirect_url
                response = self.get(redirect_url)
                redirects_followed += 1
                continue

            # Check for HX-Refresh header
            if response.get("HX-Refresh") == "true":
                # HX-Refresh means reload the current page
                self._current_url = request_headers["HX-Request-URL"]
                response = self.get(request_headers["HX-Request-URL"])
                redirects_followed += 1
                continue

            # Check for HX-Location header (more complex navigation)
            if "HX-Location" in response:
                import json

                try:
                    location_data = json.loads(response["HX-Location"])
                    path = location_data.get("path", "/")
                    self._current_url = path
                    response = self.get(path)
                    redirects_followed += 1
                    continue
                except (json.JSONDecodeError, KeyError):
                    # Invalid HX-Location header, stop following
                    break

            # No more HTMX navigation headers, return the response
            break

        if redirects_followed >= self._max_redirects:
            raise AssertionError(
                f"Exceeded maximum HTMX redirects ({self._max_redirects}). "
                "Check for redirect loops."
            )

        return response

    def _request(self, method, path, data=None, follow=False, **extra):
        """Override get() to follow HTMX redirects by default."""
        response = getattr(super(), method)(path, data=data, follow=follow, **extra)

        headers = extra.get("headers", None)
        if (
            headers is not None
            and headers.get("HX-Request", False)
            and self._follow_htmx
            and follow is not False
        ):
            response = self._follow_htmx_response(response, headers)

        return response

    def get(self, *args, **extra):
        return self._request("get", *args, **extra)

    def post(self, *args, **extra):
        return self._request("post", *args, **extra)

    def put(self, *args, **extra):
        return self._request("put", *args, **extra)

    def patch(self, *args, **extra):
        return self._request("patch", *args, **extra)

    def delete(self, *args, **extra):
        return self._request("delete", *args, **extra)


class ClientWithLoggedUserFactory(HtmxAwareClient):
    def __init__(self, user, **kwargs):
        super().__init__(**kwargs)
        self.user = user
        self.force_login(user)


class ClientWithLoggedStaffUserFactory(HtmxAwareClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        user = CollegueFactory(is_staff=True)
        self.force_login(user)

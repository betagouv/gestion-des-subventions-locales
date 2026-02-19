import time

import pytest
from django.test import Client
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTP, TOTPDevice

from gsl_core.tests.factories import CollegueFactory, PerimetreFactory


def _generate_valid_token(device):
    """Generate a valid TOTP token for the given device."""
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time()
    return totp.token()


@pytest.fixture
def staff_user(db):
    return CollegueFactory(is_staff=True, perimetre=PerimetreFactory())


@pytest.fixture
def regular_user(db):
    return CollegueFactory(is_staff=False, perimetre=PerimetreFactory())


@pytest.fixture
def staff_client(staff_user):
    client = Client()
    client.force_login(staff_user)
    return client


@pytest.fixture
def regular_client(regular_user):
    client = Client()
    client.force_login(regular_user)
    return client


class TestOTPMiddlewareEnforcement:
    def test_staff_without_device_redirected_to_setup(self, staff_client):
        response = staff_client.get("/")
        assert response.status_code == 302
        assert response["Location"] == reverse("otp-setup")

    def test_staff_with_confirmed_device_redirected_to_verify(
        self, staff_client, staff_user
    ):
        TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        response = staff_client.get("/")
        assert response.status_code == 302
        assert response["Location"].startswith(reverse("otp-verify"))

    def test_staff_with_confirmed_device_redirect_preserves_next(
        self, staff_client, staff_user
    ):
        TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        response = staff_client.get("/projets/")
        assert response.status_code == 302
        assert "next=%2Fprojets%2F" in response["Location"]

    def test_staff_after_verification_passes_through(self, staff_client, staff_user):
        device = TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        token = _generate_valid_token(device)
        staff_client.post(reverse("otp-verify"), {"token": token, "next": "/"})
        # After OTP verification, accessing / should not redirect to OTP anymore
        response = staff_client.get("/", follow=True)
        assert response.status_code == 200

    def test_non_staff_user_unaffected(self, regular_client):
        response = regular_client.get("/", follow=True)
        # Non-staff user should not see any OTP redirect
        assert response.status_code == 200
        for url, _ in response.redirect_chain:
            assert "otp" not in url

    def test_admin_pages_require_otp(self, staff_client):
        response = staff_client.get("/admin/")
        assert response.status_code == 302
        assert response["Location"] == reverse("otp-setup")

    def test_otp_urls_are_exempt(self, staff_client):
        response = staff_client.get(reverse("otp-setup"))
        assert response.status_code == 200

        response = staff_client.get(reverse("otp-verify"))
        assert response.status_code == 200

    def test_login_logout_urls_are_exempt(self, staff_client):
        response = staff_client.get(reverse("login"))
        assert response.status_code == 200

    def test_oidc_urls_are_exempt(self, staff_client):
        response = staff_client.get("/oidc/authenticate/")
        # OIDC redirects to the provider, so 302 is expected (not an OTP redirect)
        assert response.status_code == 302
        assert "otp" not in response["Location"]


class TestOTPSetupFlow:
    def test_setup_page_renders_qr_code(self, staff_client):
        response = staff_client.get(reverse("otp-setup"))
        assert response.status_code == 200
        assert "<svg" in response.content.decode()

    def test_setup_creates_unconfirmed_device(self, staff_client, staff_user):
        staff_client.get(reverse("otp-setup"))
        device = TOTPDevice.objects.get(user=staff_user)
        assert device.confirmed is False

    def test_setup_reuses_existing_unconfirmed_device(self, staff_client, staff_user):
        staff_client.get(reverse("otp-setup"))
        staff_client.get(reverse("otp-setup"))
        assert TOTPDevice.objects.filter(user=staff_user, confirmed=False).count() == 1

    def test_setup_valid_token_confirms_device(self, staff_client, staff_user):
        staff_client.get(reverse("otp-setup"))
        device = TOTPDevice.objects.get(user=staff_user)
        token = _generate_valid_token(device)

        response = staff_client.post(reverse("otp-setup"), {"token": token})
        assert response.status_code == 302
        assert response["Location"] == "/"

        device.refresh_from_db()
        assert device.confirmed is True

    def test_setup_invalid_token_shows_error(self, staff_client):
        staff_client.get(reverse("otp-setup"))
        response = staff_client.post(reverse("otp-setup"), {"token": "000000"})
        assert response.status_code == 200
        assert "Code invalide" in response.content.decode()

    def test_setup_redirects_non_staff(self, regular_client):
        response = regular_client.get(reverse("otp-setup"))
        assert response.status_code == 302
        assert response["Location"] == "/"


class TestOTPVerifyFlow:
    def test_verify_valid_token_succeeds(self, staff_client, staff_user):
        device = TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        token = _generate_valid_token(device)

        response = staff_client.post(
            reverse("otp-verify"), {"token": token, "next": "/"}
        )
        assert response.status_code == 302
        assert response["Location"] == "/"

    def test_verify_invalid_token_shows_error(self, staff_client, staff_user):
        TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")

        response = staff_client.post(
            reverse("otp-verify"), {"token": "000000", "next": "/"}
        )
        assert response.status_code == 200
        assert "Code invalide" in response.content.decode()

    def test_verify_preserves_next_url(self, staff_client, staff_user):
        device = TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        token = _generate_valid_token(device)

        response = staff_client.post(
            reverse("otp-verify"), {"token": token, "next": "/admin/"}
        )
        assert response.status_code == 302
        assert response["Location"] == "/admin/"

    def test_verify_rejects_external_next_url(self, staff_client, staff_user):
        device = TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        token = _generate_valid_token(device)

        response = staff_client.post(
            reverse("otp-verify"), {"token": token, "next": "https://evil.com"}
        )
        assert response.status_code == 302
        assert response["Location"] == "/"

    def test_verify_rejects_protocol_relative_next_url(self, staff_client, staff_user):
        device = TOTPDevice.objects.create(user=staff_user, confirmed=True, name="test")
        token = _generate_valid_token(device)

        response = staff_client.post(
            reverse("otp-verify"), {"token": token, "next": "//evil.com"}
        )
        assert response.status_code == 302
        assert response["Location"] == "/"

    def test_verify_redirects_non_staff(self, regular_client):
        response = regular_client.get(reverse("otp-verify"))
        assert response.status_code == 302
        assert response["Location"] == "/"

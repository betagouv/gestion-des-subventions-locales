import pytest
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice


@pytest.fixture
def otp_verified_client(client):
    """Returns a function to force_login a staff user with OTP auto-verified."""

    def _force_login_with_otp(user):
        client.force_login(user)
        if user.is_staff:
            device, _ = TOTPDevice.objects.get_or_create(
                user=user, defaults={"name": "test", "confirmed": True}
            )
            if not device.confirmed:
                device.confirmed = True
                device.save()
            session = client.session
            session[DEVICE_ID_SESSION_KEY] = device.persistent_id
            session.save()
        return client

    return _force_login_with_otp

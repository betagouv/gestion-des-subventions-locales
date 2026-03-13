import pytest
from django.urls import reverse

from gsl_core.tests.factories import CollegueFactory


@pytest.fixture
def superuser(db):
    return CollegueFactory(
        is_staff=True,
        is_superuser=True,
        username="superuser",
    )


@pytest.fixture
def staff_user(db):
    return CollegueFactory(
        is_staff=True,
        is_superuser=False,
        username="staffuser",
    )


@pytest.fixture
def target_user(db):
    return CollegueFactory(
        is_staff=True,
        is_superuser=False,
        username="targetuser",
    )


@pytest.mark.django_db
class TestCollegueAdminReadonlyFields:
    def test_superuser_can_edit_is_superuser_and_is_staff(
        self, otp_verified_client, superuser, target_user
    ):
        client = otp_verified_client(superuser)
        url = reverse("admin:gsl_core_collegue_change", args=[target_user.pk])
        response = client.get(url)

        content = response.content.decode()
        # For superusers, is_superuser and is_staff should be editable (checkboxes, not readonly)
        assert 'name="is_superuser"' in content
        assert 'name="is_staff"' in content

    def test_staff_user_sees_is_superuser_and_is_staff_as_readonly(
        self, otp_verified_client, staff_user, target_user
    ):
        client = otp_verified_client(staff_user)
        url = reverse("admin:gsl_core_collegue_change", args=[target_user.pk])
        response = client.get(url)

        content = response.content.decode()
        # For staff non-superusers, these fields should be readonly (no input with that name)
        assert 'name="is_superuser"' not in content
        assert 'name="is_staff"' not in content

    def test_staff_user_cannot_escalate_to_superuser_via_post(
        self, otp_verified_client, staff_user, target_user
    ):
        client = otp_verified_client(staff_user)
        url = reverse("admin:gsl_core_collegue_change", args=[target_user.pk])

        # Attempt to set is_superuser=True via POST
        client.post(
            url,
            {
                "username": target_user.username,
                "is_active": "on",
                "is_staff": "on",
                "is_superuser": "on",
                "date_joined_0": "2025-01-01",
                "date_joined_1": "00:00:00",
                "_save": "Save",
            },
        )

        target_user.refresh_from_db()
        assert not target_user.is_superuser

    def test_staff_user_cannot_remove_own_staff_status_via_post(
        self, otp_verified_client, staff_user
    ):
        """Staff user cannot modify is_staff even on their own account."""
        client = otp_verified_client(staff_user)
        url = reverse("admin:gsl_core_collegue_change", args=[staff_user.pk])

        client.post(
            url,
            {
                "username": staff_user.username,
                "is_active": "on",
                # is_staff omitted (unchecked) — should be ignored since readonly
                "date_joined_0": "2025-01-01",
                "date_joined_1": "00:00:00",
                "_save": "Save",
            },
        )

        staff_user.refresh_from_db()
        assert staff_user.is_staff

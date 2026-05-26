import re

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from gsl_core.admin_alerts import notify_admins
from gsl_core.models import Departement
from gsl_core.tests.factories import (
    CollegueFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
    RegionFactory,
)
from gsl_demarches_simplifiees.tests.factories import ProfileFactory


@pytest.fixture
def superuser(db):
    return CollegueFactory(
        is_staff=True,
        is_superuser=True,
        username="alerts_superuser",
        email="alerts_superuser@example.fr",
    )


@pytest.fixture
def admin_alert_recipients():
    with override_settings(ADMIN_ALERT_RECIPIENTS=["ops@test.local"]):
        yield ["ops@test.local"]


def _change_user_payload(user, **overrides):
    data = {
        "username": user.username,
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "comment": user.comment or "",
        "proconnect_uid": user.proconnect_uid or "",
        "proconnect_siret": user.proconnect_siret or "",
        "proconnect_chorusdt": user.proconnect_chorusdt or "",
        "date_joined_0": user.date_joined.strftime("%Y-%m-%d"),
        "date_joined_1": user.date_joined.strftime("%H:%M:%S"),
        "_save": "Save",
    }
    if user.is_active:
        data["is_active"] = "on"
    if user.is_staff:
        data["is_staff"] = "on"
    if user.is_superuser:
        data["is_superuser"] = "on"
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestNotifyAdminsHelper:
    def test_no_recipients_is_noop(self, settings):
        settings.ADMIN_ALERT_RECIPIENTS = []
        mail.outbox = []
        notify_admins("subject", "body")
        assert mail.outbox == []

    def test_sends_when_recipients_configured(self, admin_alert_recipients, settings):
        mail.outbox = []
        notify_admins("subject", "body")
        assert len(mail.outbox) == 1
        m = mail.outbox[0]
        assert m.to == ["ops@test.local"]
        assert f"[Turgot {settings.ENV}]" in m.subject
        assert "subject" in m.subject
        assert m.body == "body"


@pytest.mark.django_db
class TestCollegueAdminAlerts:
    def test_basic_user_creation_via_admin_sends_no_alert(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        """Création d'un utilisateur de base (ni staff/superuser ni périmètre)
        ne déclenche pas d'alerte ; les alertes sont émises lors d'une
        élévation ultérieure (couvertes par les tests d'octroi de droits)."""
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_collegue_add")
        response = client.post(
            url,
            {
                "username": "newuser",
                "password1": "Abc!def123ghi456",
                "password2": "Abc!def123ghi456",
            },
        )
        assert response.status_code in (200, 302)
        assert mail.outbox == []

    def test_grant_is_staff_sends_alert(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        target = CollegueFactory(
            is_staff=False, is_superuser=False, username="grantable"
        )
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_collegue_change", args=[target.pk])
        client.post(url, _change_user_payload(target, is_staff="on"))
        target.refresh_from_db()
        assert target.is_staff
        assert any("is_staff" in m.subject for m in mail.outbox)

    def test_grant_is_superuser_sends_alert(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        target = CollegueFactory(
            is_staff=True, is_superuser=False, username="superable"
        )
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_collegue_change", args=[target.pk])
        client.post(url, _change_user_payload(target, is_superuser="on"))
        target.refresh_from_db()
        assert target.is_superuser
        assert any("is_superuser" in m.subject for m in mail.outbox)

    def test_associate_ds_profile_sends_alert(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        profile = ProfileFactory(ds_email="dn@example.fr")
        target = CollegueFactory(
            is_staff=True, is_superuser=False, username="associable"
        )
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_collegue_change", args=[target.pk])
        client.post(url, _change_user_payload(target, ds_profile=str(profile.pk)))
        target.refresh_from_db()
        assert target.ds_profile_id == profile.pk
        assert any("Profil DN associé" in m.subject for m in mail.outbox)

    def test_no_alert_when_recipients_empty(self, otp_verified_client, superuser):
        target = CollegueFactory(is_staff=False, username="silent")
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_collegue_change", args=[target.pk])
        with override_settings(ADMIN_ALERT_RECIPIENTS=[]):
            client.post(url, _change_user_payload(target, is_staff="on"))
        assert mail.outbox == []

    def test_import_users_sends_recap(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        region = RegionFactory(insee_code="84", name="Auvergne-Rhône-Alpes")
        dept = DepartementFactory(insee_code="01", name="AIN", region=region)
        perimetre = PerimetreDepartementalFactory(
            departement=dept, region=region, arrondissement=None
        )
        existing = CollegueFactory(
            email="existing@ain.gouv.fr",
            username="existing@ain.gouv.fr",
            first_name="Old",
            last_name="Name",
            perimetre=perimetre,
        )
        csv_content = (
            "email,departement_code,arrondissement_code,first_name,last_name\n"
            "new@ain.gouv.fr,01,,Jean,Dupont\n"
            "existing@ain.gouv.fr,01,,New,Name\n"
        )
        client = otp_verified_client(superuser)
        mail.outbox = []

        upload_url = reverse("admin:gsl_core_collegue_import")
        upload = SimpleUploadedFile(
            "users.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )
        response = client.post(upload_url, {"format": "0", "import_file": upload})
        assert response.status_code == 200

        content = response.content.decode("utf-8")
        import_file_name = re.search(
            r'name="import_file_name" value="([^"]+)"', content
        ).group(1)
        original_file_name_match = re.search(
            r'name="original_file_name" value="([^"]+)"', content
        )

        confirm_url = reverse("admin:gsl_core_collegue_process_import")
        confirm_data = {"import_file_name": import_file_name, "format": "0"}
        if original_file_name_match:
            confirm_data["original_file_name"] = original_file_name_match.group(1)
        response = client.post(confirm_url, confirm_data)
        assert response.status_code == 302

        existing.refresh_from_db()
        assert existing.first_name == "New"

        recap = [m for m in mail.outbox if "Import groupé d'utilisateurs" in m.subject]
        assert len(recap) == 1, [m.subject for m in mail.outbox]
        body = recap[0].body
        assert "1 créé(s)" in recap[0].subject
        assert "1 mis à jour" in recap[0].subject
        assert "new@ain.gouv.fr" in body
        assert "existing@ain.gouv.fr" in body

    def test_associate_ds_profile_bulk_action_sends_recap(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        profile = ProfileFactory(ds_email="recap@example.fr")
        target = CollegueFactory(username="bulky", email="recap@example.fr")
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_collegue_changelist")
        client.post(
            url,
            {
                "action": "associate_ds_profile_to_users",
                "_selected_action": [str(target.pk)],
            },
        )
        target.refresh_from_db()
        assert target.ds_profile_id == profile.pk
        assert any("Association DN groupée" in m.subject for m in mail.outbox), [
            m.subject for m in mail.outbox
        ]


@pytest.mark.django_db
class TestDepartementAdminAlerts:
    def test_save_model_activation_sends_alert(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        dpt = DepartementFactory(insee_code="42", name="Loire", active=False)
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_departement_change", args=[dpt.pk])
        client.post(
            url,
            {
                "insee_code": dpt.insee_code,
                "name": dpt.name,
                "region": dpt.region_id,
                "active": "on",
                "_save": "Save",
            },
        )
        dpt.refresh_from_db()
        assert dpt.active
        assert any("Département activé" in m.subject for m in mail.outbox)

    def test_bulk_activate_sends_recap(
        self, otp_verified_client, superuser, admin_alert_recipients
    ):
        d1 = DepartementFactory(insee_code="91", name="Essonne", active=False)
        d2 = DepartementFactory(insee_code="92", name="Hauts-de-Seine", active=False)
        client = otp_verified_client(superuser)
        mail.outbox = []
        url = reverse("admin:gsl_core_departement_changelist")
        client.post(
            url,
            {
                "action": "activate_departement",
                "_selected_action": [d1.pk, d2.pk],
            },
        )
        assert Departement.objects.get(pk=d1.pk).active
        assert Departement.objects.get(pk=d2.pk).active
        recap = [m for m in mail.outbox if "Activation groupée" in m.subject]
        assert len(recap) == 1
        assert "Essonne" in recap[0].body
        assert "Hauts-de-Seine" in recap[0].body


@pytest.mark.django_db
class TestLockoutAlert:
    def test_lockout_signal_sends_alert(self, admin_alert_recipients):
        from axes.signals import user_locked_out

        mail.outbox = []

        class _FakeRequest:
            META = {"HTTP_USER_AGENT": "pytest"}

        user_locked_out.send(
            sender=None,
            request=_FakeRequest(),
            username="bruteforced",
            ip_address="1.2.3.4",
        )
        assert len(mail.outbox) == 1
        assert "Utilisateur bloqué" in mail.outbox[0].subject
        assert "bruteforced" in mail.outbox[0].body
        assert "1.2.3.4" in mail.outbox[0].body

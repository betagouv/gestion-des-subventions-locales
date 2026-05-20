from django.core.exceptions import ValidationError
from django.test import TestCase

from gsl_demarches_simplifiees.tests.factories import DemarcheFactory
from gsl_ds_proxy.admin import ProxyTokenAdminForm
from gsl_ds_proxy.tests.factories import ProxyTokenFactory


def _raw_ds_data(groupes):
    return {"groupeInstructeurs": groupes}


class ProxyTokenAdminFormTest(TestCase):
    def test_groupe_field_disabled_without_raw_ds_data(self):
        demarche = DemarcheFactory(raw_ds_data=None)
        token = ProxyTokenFactory(
            demarche=demarche,
            is_active=False,
            groupe_instructeur_ds_id="",
        )
        form = ProxyTokenAdminForm(instance=token)
        self.assertTrue(form.fields["groupe_instructeur_ds_id"].disabled)
        self.assertIn(
            "Sauvegardez le token",
            form.fields["groupe_instructeur_ds_id"].help_text,
        )

    def test_groupes_are_offered_with_emails_in_label(self):
        demarche = DemarcheFactory(
            raw_ds_data=_raw_ds_data(
                [
                    {
                        "id": "GROUPE-1",
                        "number": 1,
                        "label": "Centre",
                        "instructeurs": [
                            {"id": "i1", "email": "a@t.fr"},
                            {"id": "i2", "email": "b@t.fr"},
                        ],
                    },
                    {
                        "id": "GROUPE-2",
                        "number": 2,
                        "label": "Nord",
                        "instructeurs": [{"id": "i3", "email": "c@t.fr"}],
                    },
                ]
            )
        )
        token = ProxyTokenFactory(
            demarche=demarche,
            is_active=False,
            groupe_instructeur_ds_id="",
        )
        form = ProxyTokenAdminForm(instance=token)
        choices = dict(form.fields["groupe_instructeur_ds_id"].choices)
        self.assertIn("GROUPE-1", choices)
        self.assertIn("GROUPE-2", choices)
        self.assertIn("Centre (#1)", choices["GROUPE-1"])
        self.assertIn("a@t.fr", choices["GROUPE-1"])
        self.assertIn("b@t.fr", choices["GROUPE-1"])

    def test_label_truncates_emails_above_threshold(self):
        emails = [{"id": f"i{i}", "email": f"u{i}@t.fr"} for i in range(8)]
        demarche = DemarcheFactory(
            raw_ds_data=_raw_ds_data(
                [
                    {
                        "id": "GROUPE-1",
                        "number": 1,
                        "label": "Big",
                        "instructeurs": emails,
                    }
                ]
            )
        )
        token = ProxyTokenFactory(
            demarche=demarche,
            is_active=False,
            groupe_instructeur_ds_id="",
        )
        form = ProxyTokenAdminForm(instance=token)
        label = dict(form.fields["groupe_instructeur_ds_id"].choices)["GROUPE-1"]
        self.assertIn("(+3)", label)


class ProxyTokenCleanTest(TestCase):
    def test_active_token_requires_groupe(self):
        demarche = DemarcheFactory(
            raw_ds_data=_raw_ds_data([{"id": "GROUPE-1", "number": 1, "label": "X"}])
        )
        token = ProxyTokenFactory.build(
            demarche=demarche,
            is_active=True,
            groupe_instructeur_ds_id="",
        )
        with self.assertRaises(ValidationError) as ctx:
            token.clean()
        self.assertIn("groupe_instructeur_ds_id", ctx.exception.message_dict)

    def test_active_token_rejects_unknown_groupe(self):
        demarche = DemarcheFactory(
            raw_ds_data=_raw_ds_data([{"id": "GROUPE-1", "number": 1, "label": "X"}])
        )
        token = ProxyTokenFactory.build(
            demarche=demarche,
            is_active=True,
            groupe_instructeur_ds_id="UNKNOWN",
        )
        with self.assertRaises(ValidationError) as ctx:
            token.clean()
        self.assertIn("groupe_instructeur_ds_id", ctx.exception.message_dict)

    def test_active_token_accepts_known_groupe(self):
        demarche = DemarcheFactory(
            raw_ds_data=_raw_ds_data([{"id": "GROUPE-1", "number": 1, "label": "X"}])
        )
        token = ProxyTokenFactory.build(
            demarche=demarche,
            is_active=True,
            groupe_instructeur_ds_id="GROUPE-1",
        )
        token.clean()

    def test_inactive_token_does_not_require_groupe(self):
        demarche = DemarcheFactory(raw_ds_data=None)
        token = ProxyTokenFactory.build(
            demarche=demarche,
            is_active=False,
            groupe_instructeur_ds_id="",
        )
        token.clean()

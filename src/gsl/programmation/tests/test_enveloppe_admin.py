import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
)
from gsl.programmation.models import Enveloppe
from gsl.programmation.tests.factories import DetrEnveloppeFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_otp(settings):
    settings.OTP_ENABLED = False


@pytest.fixture
def client():
    return ClientWithLoggedUserFactory(
        CollegueFactory(is_staff=True, is_superuser=True)
    )


def test_valider_and_invalider_dgcl_actions(client):
    selected = DetrEnveloppeFactory(annee=2027)
    other = DetrEnveloppeFactory(annee=2027)
    url = reverse("admin:gsl_programmation_enveloppe_changelist")

    client.post(url, {"action": "valider_dgcl", "_selected_action": [selected.pk]})
    selected.refresh_from_db()
    other.refresh_from_db()
    assert selected.validee_dgcl is True
    assert other.validee_dgcl is False

    client.post(url, {"action": "invalider_dgcl", "_selected_action": [selected.pk]})
    selected.refresh_from_db()
    assert selected.validee_dgcl is False


def test_changelist_filters_on_validee_dgcl(client):
    validee = DetrEnveloppeFactory(annee=2026, validee_dgcl=True)
    provisoire = DetrEnveloppeFactory(annee=2027, validee_dgcl=False)
    url = reverse("admin:gsl_programmation_enveloppe_changelist")

    response = client.get(url, {"validee_dgcl__exact": "1"})
    assert list(response.context["cl"].queryset) == [validee]

    response = client.get(url, {"validee_dgcl__exact": "0"})
    assert list(response.context["cl"].queryset) == [provisoire]


def test_validee_dgcl_is_editable_in_change_form(client):
    enveloppe = DetrEnveloppeFactory(annee=2027)
    response = client.get(
        reverse("admin:gsl_programmation_enveloppe_change", args=[enveloppe.pk])
    )
    assert "validee_dgcl" in response.context["adminform"].form.fields


@pytest.mark.parametrize("enveloppes_officielles", (True, False))
def test_import_sets_validee_dgcl_from_checkbox(client, enveloppes_officielles):
    departement = DepartementFactory(insee_code="01")
    PerimetreDepartementalFactory(
        departement=departement, region=departement.region, arrondissement=None
    )
    upload = SimpleUploadedFile(
        "enveloppes.csv", b"montant,annee,perimetre\n1000,2027,01\n"
    )
    import_data = {"resource": "0", "format": "0", "import_file": upload}
    if enveloppes_officielles:
        import_data["enveloppes_officielles"] = "on"

    response = client.post(
        reverse("admin:gsl_programmation_enveloppe_import"), import_data
    )
    assert response.status_code == 200
    confirm_form = response.context["confirm_form"]
    assert confirm_form.initial["enveloppes_officielles"] is enveloppes_officielles

    content = response.content.decode()
    confirm_data = {
        name: re.search(rf'name="{name}" value="([^"]*)"', content).group(1)
        for name in ("import_file_name", "original_file_name", "format", "resource")
    }
    if enveloppes_officielles:
        confirm_data["enveloppes_officielles"] = "True"
    response = client.post(
        reverse("admin:gsl_programmation_enveloppe_process_import"), confirm_data
    )
    assert response.status_code == 302

    enveloppe = Enveloppe.objects.get(annee=2027, perimetre__departement=departement)
    assert enveloppe.validee_dgcl is enveloppes_officielles

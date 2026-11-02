import openpyxl
import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl.core.tests.factories import (
    ClientWithLoggedStaffUserFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
)

from ..forms import IMPORT_PREFIX
from ..models import SuiviFinancier
from ..tasks import import_chorus_file_task
from .test_extract_from_chorus import DETR_LINE, write_chorus_xlsx

IMPORT_URL = reverse("admin:gsl_chorus_suivifinancier_import_chorus")
CHANGELIST_URL = reverse("admin:gsl_chorus_suivifinancier_changelist")


def upload(path, name="chorus.xlsx"):
    with open(path, "rb") as f:
        return SimpleUploadedFile(name, f.read())


@pytest.fixture
def staff_client(db):
    return ClientWithLoggedStaffUserFactory()


def test_changelist_links_to_import_form(staff_client):
    response = staff_client.get(CHANGELIST_URL)

    assert response.status_code == 200
    assert IMPORT_URL in response.content.decode()


def test_import_form_is_displayed(staff_client):
    response = staff_client.get(IMPORT_URL)

    assert response.status_code == 200
    assert 'enctype="multipart/form-data"' in response.content.decode()


def test_import_valid_file(staff_client, tmp_path):
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE])

    response = staff_client.post(IMPORT_URL, {"file": upload(path)})

    assert response.status_code == 302
    assert response.url == CHANGELIST_URL
    ligne = SuiviFinancier.objects.get()
    assert ligne.ej == "2105003612"
    assert ligne.dn == 28281965
    # The uploaded file is removed once imported.
    dirs, _ = default_storage.listdir(IMPORT_PREFIX)
    assert all(default_storage.listdir(f"{IMPORT_PREFIX}/{d}")[1] == [] for d in dirs)


def test_import_file_with_missing_headers(staff_client, tmp_path):
    workbook = openpyxl.Workbook()
    workbook.active.append(["foo", "bar"])
    path = tmp_path / "bad.xlsx"
    workbook.save(path)

    response = staff_client.post(IMPORT_URL, {"file": upload(path)})

    assert response.status_code == 200
    assert "En-têtes introuvables" in response.content.decode()
    assert not SuiviFinancier.objects.exists()


def test_import_file_with_wrong_extension(staff_client, tmp_path):
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE])

    response = staff_client.post(IMPORT_URL, {"file": upload(path, "chorus.csv")})

    assert response.status_code == 200
    assert not SuiviFinancier.objects.exists()


def test_import_invalid_xlsx(staff_client):
    file = SimpleUploadedFile("chorus.xlsx", b"not a zip")

    response = staff_client.post(IMPORT_URL, {"file": file})

    assert response.status_code == 200
    assert "n&#x27;est pas un XLSX valide" in response.content.decode()


@pytest.mark.django_db
def test_non_staff_cannot_import(tmp_path):
    client = ClientWithLoggedUserFactory(CollegueFactory(is_staff=False))
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE])

    response = client.post(IMPORT_URL, {"file": upload(path)})

    assert response.status_code == 302
    assert "login" in response.url
    assert not SuiviFinancier.objects.exists()


@pytest.mark.django_db
def test_task_returns_import_summary(tmp_path):
    duplicate = dict(DETR_LINE)
    no_montant = {**DETR_LINE, "ej": "2105000009", "montant": ""}
    path = write_chorus_xlsx(
        tmp_path / "chorus.xlsx", [DETR_LINE, duplicate, no_montant]
    )
    key = default_storage.save(f"{IMPORT_PREFIX}/test/chorus.xlsx", upload(path))

    result = import_chorus_file_task.delay(key).get()

    assert result == {"imported": 1, "matched": 0, "duplicate": 1, "skipped": 1}

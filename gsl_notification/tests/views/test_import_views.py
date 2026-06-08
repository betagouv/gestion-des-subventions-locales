import io
import json
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from pikepdf import Pdf

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.models import DocumentImportJob, LettreEtArreteSignes
from gsl_notification.tests.factories import (
    LettreNotificationFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR

pytestmark = pytest.mark.django_db

HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def _mock_logo():
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        yield


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def user(perimetre):
    return CollegueFactory(perimetre=perimetre)


@pytest.fixture
def client(user):
    return ClientWithLoggedUserFactory(user)


def _build_pdf_for_pp(ds_number, content_blocks=200, perimetre=None):
    """Create a PP (with the given ds_number) and return (pp, pdf bytes).

    Pass `perimetre` to place the underlying projet in a specific perimetre so
    the now-scoped web import can (or cannot) see it.
    """
    from gsl_notification.utils import generate_pdf_for_generated_document

    extra = {}
    if perimetre is not None:
        extra["dotation_projet__projet__dossier_ds__perimetre"] = perimetre

    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__ds_number=ds_number,
        dotation_projet__dotation=DOTATION_DETR,
        **extra,
    )
    modele = ModeleLettreNotificationFactory(
        dotation=pp.dotation,
        perimetre=pp.dotation_projet.projet.dossier_ds.perimetre,
    )
    document = LettreNotificationFactory(
        programmation_projet=pp,
        modele=modele,
        content="<p>" + ("Contenu de test. " * content_blocks) + "</p>",
    )
    return pp, generate_pdf_for_generated_document(document)


def _split_pdf(pdf_bytes: bytes, at: int) -> tuple[bytes, bytes]:
    """Split `pdf_bytes` into two PDFs: pages [0, at) and [at, end)."""
    src = Pdf.open(io.BytesIO(pdf_bytes))
    try:
        head, tail = Pdf.new(), Pdf.new()
        for index, page in enumerate(src.pages):
            (head if index < at else tail).pages.append(page)
        head_buf, tail_buf = io.BytesIO(), io.BytesIO()
        head.save(head_buf)
        tail.save(tail_buf)
        return head_buf.getvalue(), tail_buf.getvalue()
    finally:
        src.close()


# PresignedUploadView ---------------------------------------------------------


def test_presigned_upload_returns_params(client):
    fake_s3 = MagicMock()
    fake_s3.generate_presigned_post.return_value = {
        "url": "https://s3.example.com/bucket",
        "fields": {"key": "imports/abc/scan.pdf", "policy": "..."},
    }
    with patch(
        "gsl_notification.views.import_views.get_s3_client", return_value=fake_s3
    ):
        response = client.post(
            reverse("gsl_notification:import-presigned-upload"),
            {"filename": "scan.pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://s3.example.com/bucket"
    assert "fields" in data
    assert data["key"].startswith("imports/")
    assert data["key"].endswith("/scan.pdf")


def test_presigned_upload_rejects_non_pdf(client):
    response = client.post(
        reverse("gsl_notification:import-presigned-upload"),
        {"filename": "scan.png"},
    )
    assert response.status_code == 400


def test_presigned_upload_requires_authentication():
    from django.test import Client

    response = Client().post(
        reverse("gsl_notification:import-presigned-upload"),
        {"filename": "scan.pdf"},
    )
    assert response.status_code == 302


# ImportJobStartView ----------------------------------------------------------


def test_start_view_creates_job_and_enqueues(client, user):
    keys = ["imports/abc/scan.pdf", "imports/def/scan2.pdf"]
    with patch("gsl_notification.forms.run_document_import_job.delay") as delay:
        response = client.post(
            reverse("gsl_notification:import-start"),
            # The form's hidden input carries "true" by default (checkbox checked).
            {"s3_keys": json.dumps(keys), "remove_qr_code": "true"},
            **HTMX_HEADERS,
        )

    assert response.status_code == 200
    job = DocumentImportJob.objects.get()
    assert job.created_by == user
    assert job.s3_keys == keys
    assert job.remove_qr_code is True
    delay.assert_called_once_with(str(job.pk))


def test_start_view_keeps_qr_when_remove_qr_code_is_false(client):
    keys = ["imports/abc/scan.pdf"]
    with patch("gsl_notification.forms.run_document_import_job.delay"):
        client.post(
            reverse("gsl_notification:import-start"),
            {"s3_keys": json.dumps(keys), "remove_qr_code": "false"},
            **HTMX_HEADERS,
        )

    job = DocumentImportJob.objects.get()
    assert job.remove_qr_code is False


def test_start_view_filters_out_foreign_keys(client):
    with patch("gsl_notification.forms.run_document_import_job.delay"):
        client.post(
            reverse("gsl_notification:import-start"),
            {"s3_keys": json.dumps(["imports/ok/a.pdf", "secret/elsewhere.pdf"])},
            **HTMX_HEADERS,
        )
    job = DocumentImportJob.objects.get()
    assert job.s3_keys == ["imports/ok/a.pdf"]


def test_start_view_e2e_attaches_signed_document(client, user, perimetre):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    # The web import is scoped to the importer's perimetre, so the PP must live
    # inside it for the attach to succeed.
    pp, pdf_bytes = _build_pdf_for_pp(ds_number=1234567, perimetre=perimetre)
    expected_pages = len(Pdf.open(io.BytesIO(pdf_bytes)).pages)

    fake_s3 = MagicMock()

    def _download(bucket, key, fileobj):
        fileobj.write(pdf_bytes)

    fake_s3.download_fileobj.side_effect = _download

    with patch("gsl_notification.utils.get_s3_client", return_value=fake_s3):
        response = client.post(
            reverse("gsl_notification:import-start"),
            {"s3_keys": json.dumps(["imports/abc/scan.pdf"])},
            **HTMX_HEADERS,
        )

    assert response.status_code == 200

    job = DocumentImportJob.objects.get()
    assert job.status == DocumentImportJob.STATUS_DONE
    assert job.result["files_processed"] == 1
    assert job.result["pages_extracted"] == expected_pages
    assert job.result["lettres_arretes_attached"] == 1
    assert job.result["errors"] == []

    # Temp object cleaned up after processing.
    fake_s3.delete_object.assert_called_once()

    attached = LettreEtArreteSignes.objects.get(programmation_projet=pp)
    assert f"programmation_projet_{pp.id}/" in attached.file.name


def test_start_view_merges_pages_of_same_project_across_files(client, user, perimetre):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    # Two files of the *same* import that both carry pages for the same project
    # (e.g. an arrêté file + a lettre file) must merge into a single combined
    # LettreEtArreteSignes, not have the second file replace the first.
    pp, pdf_bytes = _build_pdf_for_pp(
        ds_number=2223334, perimetre=perimetre, content_blocks=1000
    )
    total_pages = len(Pdf.open(io.BytesIO(pdf_bytes)).pages)
    assert total_pages >= 2, "test assumes a multi-page generated PDF"

    head, tail = _split_pdf(pdf_bytes, 1)
    blobs = {"imports/abc/arrete.pdf": head, "imports/abc/lettre.pdf": tail}

    fake_s3 = MagicMock()
    fake_s3.download_fileobj.side_effect = lambda b, k, f: f.write(blobs[k])

    with patch("gsl_notification.utils.get_s3_client", return_value=fake_s3):
        client.post(
            reverse("gsl_notification:import-start"),
            {"s3_keys": json.dumps(list(blobs))},
            **HTMX_HEADERS,
        )

    job = DocumentImportJob.objects.get()
    assert job.status == DocumentImportJob.STATUS_DONE
    assert job.result["files_processed"] == 2
    assert job.result["pages_extracted"] == total_pages
    assert job.result["pages_attached"] == total_pages
    assert job.result["lettres_arretes_attached"] == 1
    assert job.result["errors"] == []

    # One combined document holding every page from both files.
    docs = LettreEtArreteSignes.objects.filter(programmation_projet=pp)
    assert docs.count() == 1
    with docs.get().file.open("rb") as fh:
        assert len(Pdf.open(io.BytesIO(fh.read())).pages) == total_pages


def test_start_view_does_not_attach_out_of_perimetre(client, user):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    # PP built in a different perimetre than the importer's: the scoped lookup
    # misses it, so nothing is attached and the group is reported as failed.
    pp, pdf_bytes = _build_pdf_for_pp(ds_number=7654321, perimetre=PerimetreFactory())

    fake_s3 = MagicMock()
    fake_s3.download_fileobj.side_effect = lambda b, k, f: f.write(pdf_bytes)

    with patch("gsl_notification.utils.get_s3_client", return_value=fake_s3):
        client.post(
            reverse("gsl_notification:import-start"),
            {"s3_keys": json.dumps(["imports/abc/scan.pdf"])},
            **HTMX_HEADERS,
        )

    job = DocumentImportJob.objects.get()
    assert job.status == DocumentImportJob.STATUS_DONE
    assert job.result["lettres_arretes_attached"] == 0
    assert any(e["type"] == "group_failed" for e in job.result["errors"])
    assert not LettreEtArreteSignes.objects.filter(programmation_projet=pp).exists()


def test_start_view_reports_unreadable_pages(client, user):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    # A blank one-page PDF carries no GSL QR code, so its single page is
    # reported as unreadable and nothing is attached.
    blank = Pdf.new()
    blank.add_blank_page()
    buf = io.BytesIO()
    blank.save(buf)
    pdf_bytes = buf.getvalue()

    fake_s3 = MagicMock()
    fake_s3.download_fileobj.side_effect = lambda b, k, f: f.write(pdf_bytes)

    with patch("gsl_notification.utils.get_s3_client", return_value=fake_s3):
        client.post(
            reverse("gsl_notification:import-start"),
            {"s3_keys": json.dumps(["imports/abc/blank.pdf"])},
            **HTMX_HEADERS,
        )

    job = DocumentImportJob.objects.get()
    assert job.status == DocumentImportJob.STATUS_DONE
    assert job.result["lettres_arretes_attached"] == 0
    assert any(e["type"] == "unreadable_page" for e in job.result["errors"])


# ImportJobProgressView -------------------------------------------------------


def test_progress_view_returns_progress_while_running(client, user):
    job = DocumentImportJob.objects.create(
        created_by=user,
        s3_keys=["imports/abc/scan.pdf"],
        status=DocumentImportJob.STATUS_RUNNING,
        processed_pages=3,
    )
    response = client.get(
        reverse("gsl_notification:import-progress", kwargs={"pk": job.pk}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "every 2s" in content
    assert "3 pages traitées" in content
    # Step 2 exposes no close affordance, and carries the running marker class.
    assert 'aria-controls="import-modal"' not in content
    assert "import-step--running" in content


def test_progress_view_returns_summary_when_done(client, user):
    job = DocumentImportJob.objects.create(
        created_by=user,
        s3_keys=["imports/abc/scan.pdf"],
        status=DocumentImportJob.STATUS_DONE,
        result={
            "files_processed": 1,
            "pages_extracted": 2,
            "lettres_arretes_attached": 1,
            "errors": [],
        },
    )
    response = client.get(
        reverse("gsl_notification:import-progress", kwargs={"pk": job.pk}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Synthèse de l'importation" in content
    assert "every 2s" not in content
    # The summary step offers a close button again.
    assert 'aria-controls="import-modal"' in content


def test_progress_view_returns_summary_with_stale_warning(client, user):
    from datetime import timedelta

    from django.utils import timezone

    job = DocumentImportJob.objects.create(
        created_by=user,
        s3_keys=["imports/abc/scan.pdf"],
        status=DocumentImportJob.STATUS_RUNNING,
    )
    # Backdate past the stale cutoff (created_at is auto_now_add).
    DocumentImportJob.objects.filter(pk=job.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )

    response = client.get(
        reverse("gsl_notification:import-progress", kwargs={"pk": job.pk}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "every 2s" not in content
    assert "Traitement interrompu" in content


def test_progress_view_scoped_to_created_by(client):
    other_user = CollegueFactory(perimetre=PerimetreFactory())
    job = DocumentImportJob.objects.create(
        created_by=other_user,
        s3_keys=["imports/abc/scan.pdf"],
        status=DocumentImportJob.STATUS_RUNNING,
    )
    response = client.get(
        reverse("gsl_notification:import-progress", kwargs={"pk": job.pk}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 404

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from gsl.historique.models import ProjetAction
from gsl.projet.constants import (
    ANNEXE,
    LETTRE_ET_ARRETE_SIGNES,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED,
)
from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.models import (
    DocumentImportJob,
    LettreEtArreteSignes,
    LettreRefusSignee,
)
from gsl_notification.tests.factories import (
    AnnexeFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    ModeleLettreNotificationFactory,
)
from gsl_notification.utils import generate_pdf_for_generated_document
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory

LETTRE_REFUS_SIGNEE = LettreRefusSignee.document_type

pytestmark = pytest.mark.django_db


## FIXTURES


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def programmation_projet(perimetre):
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre
    )


@pytest.fixture
def refused_programmation_projet(perimetre):
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__status=PROJET_STATUS_REFUSED,
        status=ProgrammationProjet.STATUS_REFUSED,
    )


@pytest.fixture
def correct_perimetre_client_with_user_logged(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def different_perimetre_client_with_user_logged():
    user = CollegueFactory()
    return ClientWithLoggedUserFactory(user)


HTMX = {"HX-Request": "true"}


def _analyze_url(projet):
    return reverse(
        "fragment:gsl_notification:upload_document_analyze", kwargs={"pk": projet.id}
    )


def _attach_url(projet):
    return reverse(
        "fragment:gsl_notification:manual_document_attach", kwargs={"pk": projet.id}
    )


def _pdf(name="scan.pdf", content=b"dummy"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _parked_pdf(name="scan.pdf"):
    """A file waiting under the temporary prefix, where the analyse step leaves
    one it could not identify."""
    return default_storage.save(DocumentImportJob.temp_s3_key(name), _pdf(name))


### upload-document-analyze -----------------------------


def test_opening_the_modal_serves_a_fresh_upload_step(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    """The dialog fetches this on every opening, so a step left in error is
    never what the agent comes back to."""
    projet = programmation_projet.dotation_projet.projet

    response = correct_perimetre_client_with_user_logged.get(
        _analyze_url(projet), headers=HTMX
    )

    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/modal/projet_import/upload_step.html"
    )
    assert not response.context["form"].is_bound


def test_analyze_is_htmx_only(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    projet = programmation_projet.dotation_projet.projet

    response = correct_perimetre_client_with_user_logged.get(_analyze_url(projet))

    assert response.status_code == 400


def test_analyze_without_qr_code_asks_for_the_document_type(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    projet = programmation_projet.dotation_projet.projet

    response = correct_perimetre_client_with_user_logged.post(
        _analyze_url(projet), {"file": _pdf()}, headers=HTMX
    )

    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/modal/projet_import/choice_step.html"
    )
    form = response.context["form"]
    assert "document" in form.fields
    # Nothing has been chosen yet, so the step must not open on an error.
    assert not form.is_bound
    assert not form.errors
    assert not programmation_projet.annexes.exists()

    key = form.initial["key"]
    assert key.startswith(DocumentImportJob.TEMP_S3_PREFIX)
    assert default_storage.open(key).read() == b"dummy"


def test_analyze_of_an_image_skips_qr_detection(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    """An image can't carry a QR page, so it goes straight to the choice step."""
    projet = programmation_projet.dotation_projet.projet
    image = SimpleUploadedFile("scan.png", b"dummy", content_type="image/png")

    response = correct_perimetre_client_with_user_logged.post(
        _analyze_url(projet), {"file": image}, headers=HTMX
    )

    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/modal/projet_import/choice_step.html"
    )


def test_analyze_requires_a_file(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    projet = programmation_projet.dotation_projet.projet

    response = correct_perimetre_client_with_user_logged.post(
        _analyze_url(projet), {}, headers=HTMX
    )

    assert response.status_code == 200
    assert response.context["form"].errors["file"] == [
        "Sélectionnez un document à importer."
    ]


def test_analyze_out_of_perimetre_is_404(
    programmation_projet, different_perimetre_client_with_user_logged
):
    projet = programmation_projet.dotation_projet.projet

    response = different_perimetre_client_with_user_logged.post(
        _analyze_url(projet), {"file": _pdf()}, headers=HTMX
    )

    assert response.status_code == 404


### upload-document-analyze, QR code path -----------------------------


@pytest.fixture
def _mock_logo():
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        yield


def _signed_scan_for(programmation_projet):
    """The PDF of a generated lettre de notification, QR codes included — what
    the user gets back after printing, signing and scanning it."""
    modele = ModeleLettreNotificationFactory(
        dotation=programmation_projet.dotation,
        perimetre=programmation_projet.dotation_projet.projet.dossier_ds.perimetre,
    )
    document = LettreNotificationFactory(
        programmation_projet=programmation_projet,
        modele=modele,
        content="<p>Contenu de la lettre.</p>",
    )
    return generate_pdf_for_generated_document(document)


def test_analyze_attaches_the_document_read_from_its_qr_code(
    perimetre, correct_perimetre_client_with_user_logged, _mock_logo
):
    """The whole point of the flow: a scan carrying the QR codes is attached
    without ever asking the user what it is."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    programmation_projet = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__status=PROJET_STATUS_ACCEPTED,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    projet = programmation_projet.dotation_projet.projet
    scan = SimpleUploadedFile(
        "scan.pdf",
        _signed_scan_for(programmation_projet),
        content_type="application/pdf",
    )

    response = correct_perimetre_client_with_user_logged.post(
        _analyze_url(projet), {"file": scan}, headers=HTMX
    )

    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/modal/projet_import/summary_step.html"
    )
    assert programmation_projet.lettre_et_arrete_signes is not None
    assert ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_DOC_UPLOADED
    ).exists()


def test_analyze_refuses_a_scan_belonging_to_another_projet(
    perimetre, correct_perimetre_client_with_user_logged, _mock_logo
):
    """The QR code names another dossier: attaching it here would file the wrong
    projet's signed document, so the import is refused rather than guessed."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    other_pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__projet__dossier_ds__ds_number=9999999,
        dotation_projet__status=PROJET_STATUS_ACCEPTED,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    target_pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__projet__dossier_ds__ds_number=1111111,
        dotation_projet__status=PROJET_STATUS_ACCEPTED,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    scan = SimpleUploadedFile(
        "scan.pdf", _signed_scan_for(other_pp), content_type="application/pdf"
    )

    response = correct_perimetre_client_with_user_logged.post(
        _analyze_url(target_pp.dotation_projet.projet),
        {"file": scan},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "9999999" in response.context["form"].errors["file"][0]
    assert not LettreEtArreteSignes.objects.filter(
        programmation_projet=target_pp
    ).exists()
    assert not LettreEtArreteSignes.objects.filter(
        programmation_projet=other_pp
    ).exists()


### upload-document-attach -----------------------------


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_attach_imports_the_document(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.dotation

    response = correct_perimetre_client_with_user_logged.post(
        _attach_url(projet),
        {"key": _parked_pdf("test.pdf"), "document": f"{doc_type}-{dotation}"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/modal/projet_import/summary_step.html"
    )
    # The summary ends the flow: it carries the step wrapper htmx swaps out, so
    # it replaces the step the form posted from rather than nesting inside it.
    assert 'id="upload-document-modal-step"' in response.content.decode()

    if doc_type == LETTRE_ET_ARRETE_SIGNES:
        document = programmation_projet.lettre_et_arrete_signes
    else:
        assert programmation_projet.annexes.count() == 1
        document = programmation_projet.annexes.first()

    assert document.file.name.startswith(
        f"{doc_type}/programmation_projet_{programmation_projet.id}/test"
    )
    assert document.created_by == correct_perimetre_client_with_user_logged.user


def test_import_refreshes_the_page_behind_the_modal(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    """The summary carries what the import changed, swapped out-of-band: the
    imported documents table, and the notification step whose "Notifier" button
    a signed lettre unblocks."""
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.dotation

    response = correct_perimetre_client_with_user_logged.post(
        _attach_url(projet),
        {"key": _parked_pdf(), "document": f"{LETTRE_ET_ARRETE_SIGNES}-{dotation}"},
        headers=HTMX,
    )

    content = response.content.decode()
    assert 'id="imported-documents-block"' in content
    assert 'id="notification-message-block"' in content
    assert content.count('hx-swap-oob="true"') == 2
    assert "Il n’y a pas de document importé pour le moment." not in content


def test_attach_logs_a_projet_action(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.dotation

    correct_perimetre_client_with_user_logged.post(
        _attach_url(projet),
        {"key": _parked_pdf(), "document": f"{LETTRE_ET_ARRETE_SIGNES}-{dotation}"},
        headers=HTMX,
    )

    action = ProjetAction.objects.get(projet=projet)
    assert action.action_type == ProjetAction.TYPE_DOC_UPLOADED
    assert action.actor == correct_perimetre_client_with_user_logged.user
    assert action.dotation == dotation


def test_attach_refuses_a_type_the_dotation_status_forbids(
    refused_programmation_projet, correct_perimetre_client_with_user_logged
):
    """`lettre_et_arrete_signes` only applies to an accepted dotation, so it is
    not even offered as a choice for a refused one."""
    programmation_projet = refused_programmation_projet
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.dotation

    response = correct_perimetre_client_with_user_logged.post(
        _attach_url(projet),
        {"key": _parked_pdf(), "document": f"{LETTRE_ET_ARRETE_SIGNES}-{dotation}"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "document" in response.context["form"].errors
    assert not LettreEtArreteSignes.objects.exists()


def test_attach_imports_a_lettre_refus_signee(
    refused_programmation_projet, correct_perimetre_client_with_user_logged
):
    programmation_projet = refused_programmation_projet
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.dotation

    response = correct_perimetre_client_with_user_logged.post(
        _attach_url(projet),
        {"key": _parked_pdf(), "document": f"{LETTRE_REFUS_SIGNEE}-{dotation}"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert programmation_projet.lettre_refus_signee is not None


def test_attach_out_of_perimetre_is_404(
    programmation_projet, different_perimetre_client_with_user_logged
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.dotation

    response = different_perimetre_client_with_user_logged.post(
        _attach_url(projet),
        {"key": _parked_pdf(), "document": f"{LETTRE_ET_ARRETE_SIGNES}-{dotation}"},
        headers=HTMX,
    )

    assert response.status_code == 404


### uploaded-document-download


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_uploaded_document_download_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:uploaded-document-download",
        kwargs={"document_type": doc_type, "document_id": 1000},
    )
    assert url == f"/notification/document-televerse/{doc_type}/1000/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@override_settings(BYPASS_ANTIVIRUS=True)
@pytest.mark.parametrize(
    "doc_type, factory",
    ((LETTRE_ET_ARRETE_SIGNES, LettreEtArreteSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_download_url_with_correct_perimetre_and_with_arrete(
    correct_perimetre_client_with_user_logged, programmation_projet, doc_type, factory
):
    doc = factory(programmation_projet=programmation_projet)
    url = doc.get_download_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/download/"

    # Mock boto3.client().get_object
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.iter_chunks.return_value = [b"dummy data"]
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/pdf",
        }
        mock_boto_client.return_value = mock_s3

        response = correct_perimetre_client_with_user_logged.get(url)
        assert response.status_code == 200


@pytest.mark.parametrize(
    "doc_type, factory",
    ((LETTRE_ET_ARRETE_SIGNES, LettreEtArreteSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_download_url_without_correct_perimetre_and_without_arrete(
    different_perimetre_client_with_user_logged, doc_type, factory
):
    doc = factory()
    url = doc.get_download_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/download/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


### uploaded-document-view


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_uploaded_document_view_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:uploaded-document-view",
        kwargs={"document_type": doc_type, "document_id": 1000},
    )
    assert url == f"/notification/document-televerse/{doc_type}/1000/view/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "doc_type, factory",
    ((LETTRE_ET_ARRETE_SIGNES, LettreEtArreteSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_view_url_without_correct_perimetre_and_without_arrete(
    different_perimetre_client_with_user_logged, doc_type, factory
):
    doc = factory()
    url = doc.get_view_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/view/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404

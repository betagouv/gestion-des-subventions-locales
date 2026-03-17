from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteEtLettreSignesFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ANNEXE, ARRETE_ET_LETTRE_SIGNES

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
def client_with_user(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


## SIGNAL TESTS


@patch("gsl_notification.tasks.scan_uploaded_document")
def test_upload_triggers_scan_task_when_antivirus_enabled(
    mock_scan_task, settings, perimetre
):
    settings.BYPASS_ANTIVIRUS = False
    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre
    )
    doc = ArreteEtLettreSignesFactory(programmation_projet=pp)

    mock_scan_task.delay.assert_called_once_with(
        "gsl_notification.ArreteEtLettreSignes", doc.pk
    )


@patch("gsl_notification.tasks.scan_uploaded_document")
def test_upload_does_not_trigger_scan_when_antivirus_bypassed(
    mock_scan_task, settings, perimetre
):
    settings.BYPASS_ANTIVIRUS = True
    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre
    )
    ArreteEtLettreSignesFactory(programmation_projet=pp)

    mock_scan_task.delay.assert_not_called()


@patch("gsl_notification.tasks.scan_uploaded_document")
def test_annexe_upload_triggers_scan_task(mock_scan_task, settings, perimetre):
    settings.BYPASS_ANTIVIRUS = False
    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre
    )
    doc = AnnexeFactory(programmation_projet=pp)

    mock_scan_task.delay.assert_called_once_with("gsl_notification.Annexe", doc.pk)


## SCAN TASK TESTS


@patch("gsl_notification.tasks.subprocess.run")
def test_scan_task_marks_clean_file(mock_run, settings, programmation_projet):
    # Create document with bypass to avoid signal-triggered scan
    doc = ArreteEtLettreSignesFactory(programmation_projet=programmation_projet)
    assert doc.last_scan is None
    assert doc.is_infected is None

    settings.BYPASS_ANTIVIRUS = False
    mock_run.return_value = MagicMock(returncode=0, stdout="OK")

    from gsl_notification.tasks import scan_uploaded_document

    scan_uploaded_document("gsl_notification.ArreteEtLettreSignes", doc.pk)

    doc.refresh_from_db()
    assert doc.last_scan is not None
    assert doc.is_infected is False


@patch("gsl_notification.tasks.subprocess.run")
def test_scan_task_marks_infected_file(mock_run, settings, programmation_projet):
    doc = ArreteEtLettreSignesFactory(programmation_projet=programmation_projet)

    settings.BYPASS_ANTIVIRUS = False
    mock_run.return_value = MagicMock(returncode=1, stdout="FOUND Eicar-Test-Signature")

    from gsl_notification.tasks import scan_uploaded_document

    scan_uploaded_document("gsl_notification.ArreteEtLettreSignes", doc.pk)

    doc.refresh_from_db()
    assert doc.last_scan is not None
    assert doc.is_infected is True


@patch("gsl_notification.tasks.subprocess.run")
def test_scan_task_raises_on_clamdscan_error(mock_run, settings, programmation_projet):
    doc = ArreteEtLettreSignesFactory(programmation_projet=programmation_projet)

    settings.BYPASS_ANTIVIRUS = False
    mock_run.return_value = MagicMock(returncode=2, stdout="ERROR: some clamav error")

    from gsl_notification.tasks import scan_uploaded_document

    with pytest.raises(RuntimeError, match="clamdscan exited with code 2"):
        scan_uploaded_document("gsl_notification.ArreteEtLettreSignes", doc.pk)


def test_scan_task_skips_when_bypassed(settings, programmation_projet):
    settings.BYPASS_ANTIVIRUS = True

    doc = ArreteEtLettreSignesFactory(programmation_projet=programmation_projet)

    from gsl_notification.tasks import scan_uploaded_document

    scan_uploaded_document("gsl_notification.ArreteEtLettreSignes", doc.pk)

    doc.refresh_from_db()
    assert doc.last_scan is None
    assert doc.is_infected is None


## DOWNLOAD BLOCKING TESTS
# Documents are created with BYPASS=True (default in test settings),
# then BYPASS is set to False to test download blocking.


@pytest.mark.parametrize(
    "doc_type, factory",
    ((ARRETE_ET_LETTRE_SIGNES, ArreteEtLettreSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_download_blocked_when_never_scanned(
    settings, client_with_user, programmation_projet, doc_type, factory
):
    doc = factory(programmation_projet=programmation_projet)
    assert doc.last_scan is None

    settings.BYPASS_ANTIVIRUS = False

    url = doc.get_download_url()
    response = client_with_user.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "doc_type, factory",
    ((ARRETE_ET_LETTRE_SIGNES, ArreteEtLettreSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_download_blocked_when_infected(
    settings, client_with_user, programmation_projet, doc_type, factory
):
    doc = factory(
        programmation_projet=programmation_projet,
        last_scan=timezone.now(),
        is_infected=True,
    )

    settings.BYPASS_ANTIVIRUS = False

    url = doc.get_download_url()
    response = client_with_user.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "doc_type, factory",
    ((ARRETE_ET_LETTRE_SIGNES, ArreteEtLettreSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_download_allowed_when_clean(
    settings, client_with_user, programmation_projet, doc_type, factory
):
    doc = factory(
        programmation_projet=programmation_projet,
        last_scan=timezone.now(),
        is_infected=False,
    )

    settings.BYPASS_ANTIVIRUS = False

    url = doc.get_download_url()

    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.iter_chunks.return_value = [b"dummy data"]
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/pdf",
        }
        mock_boto_client.return_value = mock_s3

        response = client_with_user.get(url)
        assert response.status_code == 200


@pytest.mark.parametrize(
    "doc_type, factory",
    ((ARRETE_ET_LETTRE_SIGNES, ArreteEtLettreSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_download_allowed_when_bypass_even_if_never_scanned(
    settings, client_with_user, programmation_projet, doc_type, factory
):
    settings.BYPASS_ANTIVIRUS = True
    doc = factory(programmation_projet=programmation_projet)

    url = doc.get_download_url()

    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.iter_chunks.return_value = [b"dummy data"]
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/pdf",
        }
        mock_boto_client.return_value = mock_s3

        response = client_with_user.get(url)
        assert response.status_code == 200


## IS_DOWNLOADABLE PROPERTY TESTS


@pytest.mark.parametrize("factory", (ArreteEtLettreSignesFactory, AnnexeFactory))
def test_is_downloadable_false_when_never_scanned(
    settings, programmation_projet, factory
):
    settings.BYPASS_ANTIVIRUS = False
    doc = factory(programmation_projet=programmation_projet)
    assert doc.last_scan is None
    assert doc.is_downloadable is False


@pytest.mark.parametrize("factory", (ArreteEtLettreSignesFactory, AnnexeFactory))
def test_is_downloadable_false_when_infected(settings, programmation_projet, factory):
    settings.BYPASS_ANTIVIRUS = False
    doc = factory(
        programmation_projet=programmation_projet,
        last_scan=timezone.now(),
        is_infected=True,
    )
    assert doc.is_downloadable is False


@pytest.mark.parametrize("factory", (ArreteEtLettreSignesFactory, AnnexeFactory))
def test_is_downloadable_true_when_scanned_and_clean(
    settings, programmation_projet, factory
):
    settings.BYPASS_ANTIVIRUS = False
    doc = factory(
        programmation_projet=programmation_projet,
        last_scan=timezone.now(),
        is_infected=False,
    )
    assert doc.is_downloadable is True


@pytest.mark.parametrize("factory", (ArreteEtLettreSignesFactory, AnnexeFactory))
def test_is_downloadable_true_when_bypass_enabled(
    settings, programmation_projet, factory
):
    settings.BYPASS_ANTIVIRUS = True
    doc = factory(programmation_projet=programmation_projet)
    assert doc.last_scan is None
    assert doc.is_downloadable is True


def test_generated_document_is_always_downloadable(programmation_projet):
    from gsl_notification.tests.factories import ArreteFactory

    doc = ArreteFactory(programmation_projet=programmation_projet)
    assert doc.is_downloadable is True


## LOGO SCANNING SIGNAL TESTS


@pytest.mark.parametrize(
    "factory, model_label",
    (
        (ModeleArreteFactory, "gsl_notification.ModeleArrete"),
        (ModeleLettreNotificationFactory, "gsl_notification.ModeleLettreNotification"),
    ),
)
@patch("gsl_notification.tasks.scan_uploaded_document")
def test_logo_create_triggers_scan(mock_scan_task, settings, factory, model_label):
    settings.BYPASS_ANTIVIRUS = False
    doc = factory()

    mock_scan_task.delay.assert_called_once_with(model_label, doc.pk, "logo")


@pytest.mark.parametrize(
    "factory, model_label",
    (
        (ModeleArreteFactory, "gsl_notification.ModeleArrete"),
        (ModeleLettreNotificationFactory, "gsl_notification.ModeleLettreNotification"),
    ),
)
@patch("gsl_notification.tasks.scan_uploaded_document")
def test_logo_update_triggers_scan(mock_scan_task, settings, factory, model_label):
    settings.BYPASS_ANTIVIRUS = True
    doc = factory()
    mock_scan_task.delay.assert_not_called()

    settings.BYPASS_ANTIVIRUS = False
    from django.core.files.uploadedfile import SimpleUploadedFile

    doc.logo = SimpleUploadedFile("new_logo.png", b"fake-image-data")
    doc.save()

    mock_scan_task.delay.assert_called_once_with(model_label, doc.pk, "logo")


@patch("gsl_notification.tasks.scan_uploaded_document")
def test_logo_unrelated_save_does_not_trigger_scan(mock_scan_task, settings):
    settings.BYPASS_ANTIVIRUS = True
    doc = ModeleArreteFactory()
    mock_scan_task.delay.assert_not_called()

    settings.BYPASS_ANTIVIRUS = False
    doc.name = "Nouveau nom"
    doc.save(update_fields=["name"])

    mock_scan_task.delay.assert_not_called()


@pytest.mark.parametrize(
    "factory",
    (ModeleArreteFactory, ModeleLettreNotificationFactory),
)
@patch("gsl_notification.tasks.scan_uploaded_document")
def test_logo_create_does_not_trigger_scan_when_bypassed(
    mock_scan_task, settings, factory
):
    settings.BYPASS_ANTIVIRUS = True
    factory()

    mock_scan_task.delay.assert_not_called()


## LOGO SCAN TASK TESTS


@patch("gsl_notification.tasks.subprocess.run")
def test_scan_task_with_logo_field_marks_clean(mock_run, settings):
    settings.BYPASS_ANTIVIRUS = True
    doc = ModeleArreteFactory()
    assert doc.last_scan is None
    assert doc.is_infected is None

    settings.BYPASS_ANTIVIRUS = False
    mock_run.return_value = MagicMock(returncode=0, stdout="OK")

    from gsl_notification.tasks import scan_uploaded_document

    scan_uploaded_document("gsl_notification.ModeleArrete", doc.pk, "logo")

    doc.refresh_from_db()
    assert doc.last_scan is not None
    assert doc.is_infected is False


@patch("gsl_notification.tasks.subprocess.run")
def test_scan_task_with_logo_field_marks_infected(mock_run, settings):
    settings.BYPASS_ANTIVIRUS = True
    doc = ModeleArreteFactory()

    settings.BYPASS_ANTIVIRUS = False
    mock_run.return_value = MagicMock(returncode=1, stdout="FOUND Eicar-Test-Signature")

    from gsl_notification.tasks import scan_uploaded_document

    scan_uploaded_document("gsl_notification.ModeleArrete", doc.pk, "logo")

    doc.refresh_from_db()
    assert doc.last_scan is not None
    assert doc.is_infected is True


## PERIODIC SCAN INCLUDES LOGO MODELS


@patch("gsl_notification.tasks._scan_file")
def test_periodic_scan_includes_logo_models(mock_scan_file, settings):
    settings.BYPASS_ANTIVIRUS = True
    ModeleArreteFactory()
    ModeleLettreNotificationFactory()

    settings.BYPASS_ANTIVIRUS = False
    mock_scan_file.return_value = {"is_infected": False, "output": "OK"}

    from gsl_notification.tasks import scan_all_uploaded_documents

    scan_all_uploaded_documents()

    # At least 2 calls for the 2 logo models (plus any uploaded documents)
    assert mock_scan_file.call_count >= 2

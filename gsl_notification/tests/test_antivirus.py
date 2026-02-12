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

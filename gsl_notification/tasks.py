import logging
import os
import subprocess
import tempfile
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from gsl_notification.models import (
    Annexe,
    DocumentImportJob,
    LettreEtArreteSignes,
    ModeleArrete,
    ModeleLettreNotification,
)

logger = logging.getLogger(__name__)

UPLOADED_DOCUMENT_MODELS = (LettreEtArreteSignes, Annexe)
LOGO_SCANNED_MODELS = (ModeleArrete, ModeleLettreNotification)


@shared_task
def generate_export_task(job_id: str) -> None:
    from gsl_notification.exports import build_export, upload_export_and_get_url
    from gsl_notification.models import ExportJob

    job = ExportJob.objects.get(pk=job_id)
    try:
        job.status = ExportJob.STATUS_RUNNING
        job.save(update_fields=["status", "updated_at"])

        filename, content_type, body = build_export(job)
        download_url = upload_export_and_get_url(filename, content_type, body)

        ExportJob.objects.filter(pk=job.pk).update(
            status=ExportJob.STATUS_DONE,
            download_url=download_url,
            updated_at=timezone.now(),
        )
    except Exception:
        ExportJob.objects.filter(pk=job.pk).update(
            status=ExportJob.STATUS_FAILED, updated_at=timezone.now()
        )
        raise


def _scan_path(path: str) -> dict:
    """Scan a file already on disk with clamdscan.

    Returns dict with keys: is_infected (bool), output (str).
    """
    result = subprocess.run(
        [
            "clamdscan",
            f"--config-file={settings.CLAMAV_CONFIG_FILE}",
            "--fdpass",
            path,
        ],
        capture_output=True,
        text=True,
    )

    match result.returncode:
        case 0:
            return {"is_infected": False, "output": result.stdout}
        case 1:
            return {"is_infected": True, "output": result.stdout}
        case _:
            raise RuntimeError(
                f"clamdscan exited with code {result.returncode}: {result.stdout}"
            )


def _scan_file(file_field) -> dict:
    """Download a file from storage to a temp location and scan it with clamdscan.

    Returns dict with keys: is_infected (bool), output (str).
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            with file_field.open("rb") as src:
                for chunk in src.chunks():
                    tmp.write(chunk)

        return _scan_path(tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _update_scan_result(instance, scan_result):
    instance.last_scan = timezone.now()
    instance.is_infected = scan_result["is_infected"]
    instance.save(update_fields=["last_scan", "is_infected"])

    if scan_result["is_infected"]:
        logger.error(
            "Fichier infecté détecté : %s id=%s — %s",
            instance._meta.label,
            instance.pk,
            scan_result["output"],
        )


@shared_task
def scan_uploaded_document(model_label: str, pk: int, file_field_name: str = "file"):
    """Scan a single uploaded document for viruses."""
    if settings.BYPASS_ANTIVIRUS:
        return

    from django.apps import apps

    model_class = apps.get_model(model_label)
    instance = model_class.objects.get(pk=pk)

    file_field = getattr(instance, file_field_name)
    scan_result = _scan_file(file_field)
    _update_scan_result(instance, scan_result)


@shared_task
def scan_all_uploaded_documents():
    """Periodic task: rescan all uploaded documents."""
    if settings.BYPASS_ANTIVIRUS:
        return

    scanned = 0
    infected = 0

    models_and_fields = [
        (model_class, "file") for model_class in UPLOADED_DOCUMENT_MODELS
    ] + [(Model, "logo") for Model in LOGO_SCANNED_MODELS]

    for Model, field_name in models_and_fields:
        for instance in Model.objects.all().iterator():
            try:
                file_field = getattr(instance, field_name)
                scan_result = _scan_file(file_field)
                _update_scan_result(instance, scan_result)
                scanned += 1
                if scan_result["is_infected"]:
                    infected += 1
            except (FileNotFoundError, RuntimeError):
                logger.exception(
                    "Erreur lors de l'analyse de %s id=%s",
                    Model._meta.label,
                    instance.pk,
                )

    logger.info(
        "Analyse antivirus périodique terminée : %d fichiers analysés, %d infectés",
        scanned,
        infected,
    )


# Save progress to the DB every N decoded pages so the polling view advances
# without one write per page on large scans.
_PROGRESS_SAVE_EVERY = 5


def _empty_import_result() -> dict:
    return {
        "files_processed": 0,
        "pages_extracted": 0,
        "pages_attached": 0,
        "lettres_arretes_attached": 0,
        "errors": [],
    }


@shared_task
def run_document_import_job(job_id: str) -> None:
    """
    Re-import scanned, signed documents uploaded to a temporary S3 prefix.

    Download and virus-scan every uploaded PDF first (skipping & recording
    infected ones), then drain `reattach_signed_docs` over the whole batch in a
    single pass: it decodes the per-page GSL QR codes and merges page-groups
    sharing a `(ds_number, dotation)` across all files into one document per
    project. Progress and the report-only summary are stored on the job row;
    temporary S3 objects are deleted once the job completes.
    """
    from gsl_notification.utils import get_s3_client

    job = DocumentImportJob.objects.select_related("created_by").get(pk=job_id)
    result = _empty_import_result()
    try:
        job.status = DocumentImportJob.STATUS_RUNNING
        job.save(update_fields=["status", "updated_at"])

        s3 = get_s3_client()
        bucket = settings.AWS_STORAGE_BUCKET_NAME

        files = _download_and_scan_all(job, s3, bucket, result)
        _reattach_all_files(job, files, result)

        _delete_temp_objects(s3, bucket, job.s3_keys)

        job.result = result
        job.status = DocumentImportJob.STATUS_DONE
        # total_pages/processed_pages are maintained exclusively via F()
        # expressions in this task; writing the stale in-memory values here
        # would clobber the accumulated counters, so they stay out.
        job.save(update_fields=["result", "status", "updated_at"])
    finally:
        # Safety net: if an unexpected exception propagated out, mark the job
        # DONE with a crash sentinel so the UI stops polling, then re-raise so
        # Celery and Sentry see the traceback.
        current = DocumentImportJob.objects.filter(pk=job.pk).only("status").first()
        if current is not None and current.status != DocumentImportJob.STATUS_DONE:
            result["errors"].append(
                {
                    "type": "crash",
                    "message": "Erreur inattendue : le traitement a été interrompu.",
                }
            )
            DocumentImportJob.objects.filter(pk=job.pk).update(
                result=result,
                status=DocumentImportJob.STATUS_DONE,
                updated_at=timezone.now(),
            )


def _download_and_scan_all(job, s3, bucket, result) -> list[tuple[str, bytes]]:
    """Download and virus-scan every uploaded file, returning the surviving
    `(stem, pdf_bytes)` list. Infected files are skipped and recorded in
    `result` so the batch decode below sees only clean PDFs."""
    files: list[tuple[str, bytes]] = []
    for s3_key in job.s3_keys:
        stem = Path(s3_key).stem
        pdf_bytes = _download_and_scan(s3, bucket, s3_key, stem, result)
        if pdf_bytes is not None:
            files.append((stem, pdf_bytes))
    return files


def _reattach_all_files(job, files, result) -> None:
    """Drain `reattach_signed_docs` over the whole batch, merging page-groups
    across files. Progress is saved every few pages so the polling view
    advances without one DB write per page on large scans."""
    if not files:
        return

    from gsl_notification.reattach import reattach_signed_docs

    events = _consume_reattach_events(
        reattach_signed_docs(
            files,
            job.created_by,
            restrict_to_user_perimetre=True,
            remove_qr_code=job.remove_qr_code,
        ),
        job,
        result,
    )
    pages_since_save = 0
    for _ in events:
        pages_since_save += 1
        if pages_since_save >= _PROGRESS_SAVE_EVERY:
            _bump_processed_pages(job, pages_since_save)
            pages_since_save = 0
    _bump_processed_pages(job, pages_since_save)

    result["files_processed"] += len(files)


def _download_and_scan(s3, bucket, s3_key, stem, result) -> bytes | None:
    """Download `s3_key` to a temp file and virus-scan it. Return the PDF bytes,
    or None (recording an error) if the file is infected."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            s3.download_fileobj(bucket, s3_key, tmp)

        if not settings.BYPASS_ANTIVIRUS:
            scan_result = _scan_path(tmp_path)
            if scan_result["is_infected"]:
                logger.error("Fichier importé infecté : %s — %s", s3_key, scan_result)
                result["errors"].append(
                    {
                        "type": "infected_file",
                        "file": stem,
                        "message": "Fichier identifié comme infecté, ignoré.",
                    }
                )
                return None

        return Path(tmp_path).read_bytes()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _consume_reattach_events(events, job, result):
    """Update counters/report from each reattach event, yielding once per
    processed page so the caller can track progress.

    Each page event carries the stem of the source file it belongs to.
    Only page events (PageDecoded/UnreadablePage) yield; GroupAttached and
    GroupFailed mutate `result` without yielding, so they are applied lazily
    when the caller drives the generator to its final `next()`.
    """
    from gsl_notification.reattach import (
        DecodeStarted,
        GroupAttached,
        GroupFailed,
        PageDecoded,
        UnreadablePage,
    )

    for event in events:
        if isinstance(event, DecodeStarted):
            DocumentImportJob.objects.filter(pk=job.pk).update(
                total_pages=F("total_pages") + event.total_pages,
                updated_at=timezone.now(),
            )
            result["pages_extracted"] += event.total_pages
        elif isinstance(event, (PageDecoded, UnreadablePage)):
            if isinstance(event, UnreadablePage):
                result["errors"].append(
                    {
                        "type": "unreadable_page",
                        "file": event.file,
                        "scan_page": event.scan_page,
                    }
                )
            yield event
        elif isinstance(event, GroupAttached):
            result["lettres_arretes_attached"] += 1
            result["pages_attached"] += sum(
                len(pages) for pages in event.report.pages_by_doc_type.values()
            )
        elif isinstance(event, GroupFailed):
            result["errors"].append(
                {
                    "type": "group_failed",
                    "ds_number": event.report.ds_number,
                    "dotation": event.report.dotation,
                    "message": event.report.error,
                }
            )


def _bump_processed_pages(job, processed: int) -> None:
    if processed:
        DocumentImportJob.objects.filter(pk=job.pk).update(
            processed_pages=F("processed_pages") + processed,
            updated_at=timezone.now(),
        )


def _delete_temp_objects(s3, bucket, s3_keys) -> None:
    for s3_key in s3_keys:
        s3.delete_object(Bucket=bucket, Key=s3_key)

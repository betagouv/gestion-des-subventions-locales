import io
import logging
import tempfile
import uuid
import zipfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify
from pikepdf import Pdf

from gsl.notification.forms.bulk_generation import (
    ARRETE_ET_LETTRE,
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
)
from gsl.notification.models import ExportJob, GeneratedDocument
from gsl.notification.utils import (
    count_pdf_pages,
    generate_pdf_pass1,
    generate_pdf_pass2,
)

logger = logging.getLogger(__name__)

EXPORT_PREFIX = "tmp/notifications/exports"
EXPORT_URL_TTL = 900  # 15 minutes


def build_export(job) -> tuple[str, str, bytes]:
    queryset = GeneratedDocument.objects.filter(
        enveloppe_projet_id__in=job.enveloppe_projet_ids, type__in=job.attr_names
    ).select_related(
        "modele",
        "enveloppe_projet__enveloppe",
        "enveloppe_projet__projet__dossier_ds__ds_demandeur",
    )
    by_key = {(doc.enveloppe_projet_id, doc.type): doc for doc in queryset}
    documents_by_projet = [
        [by_key[(enveloppe_projet_id, attr)] for attr in job.attr_names]
        for enveloppe_projet_id in job.enveloppe_projet_ids
    ]
    documents = _grouped_by_projet(documents_by_projet)
    total = len(documents)
    total_steps = 3 if job.with_qr_code else 2

    ExportJob.objects.filter(pk=job.pk).update(
        total=total, total_steps=total_steps, updated_at=timezone.now()
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_paths = _render_pdfs_to_disk(job, documents, Path(tmp_dir))

        ExportJob.objects.filter(pk=job.pk).update(
            step=total_steps, updated_at=timezone.now()
        )

        return _assemble_export(
            documents_by_projet, job.export_format, job.document_type, pdf_paths
        )


def _render_pdfs_to_disk(job, documents, tmp_path: Path) -> dict[int, Path]:
    if job.with_qr_code:
        ExportJob.objects.filter(pk=job.pk).update(
            step=1, processed=0, updated_at=timezone.now()
        )
        page_counts: dict[int, int] = {}
        for doc in documents:
            pdf = generate_pdf_pass1(doc)
            page_counts[doc.pk] = count_pdf_pages(pdf)
            ExportJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1, updated_at=timezone.now()
            )

        ExportJob.objects.filter(pk=job.pk).update(
            step=2, processed=0, updated_at=timezone.now()
        )
        pdf_paths: dict[int, Path] = {}
        for doc in documents:
            pdf = generate_pdf_pass2(doc, page_counts[doc.pk])
            path = tmp_path / f"{doc.pk}.pdf"
            path.write_bytes(pdf)
            pdf_paths[doc.pk] = path
            ExportJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1, updated_at=timezone.now()
            )
    else:
        ExportJob.objects.filter(pk=job.pk).update(
            step=1, processed=0, updated_at=timezone.now()
        )
        pdf_paths = {}
        for doc in documents:
            pdf = generate_pdf_pass1(doc)
            path = tmp_path / f"{doc.pk}.pdf"
            path.write_bytes(pdf)
            pdf_paths[doc.pk] = path
            ExportJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1, updated_at=timezone.now()
            )

    return pdf_paths


def _assemble_export(
    documents_by_projet, export_format, document_type, pdf_paths: dict[int, Path]
) -> tuple[str, str, bytes]:
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL:
        return _build_single_merged_pdf(documents_by_projet, document_type, pdf_paths)
    if export_format == EXPORT_FORMAT_ONE_PDF_PER_PROJECT:
        return _build_one_pdf_per_project(documents_by_projet, pdf_paths)
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED:
        return _build_grouped_merged_pdf(documents_by_projet, pdf_paths)
    return _build_one_pdf_per_doc(documents_by_projet, pdf_paths)


def _build_one_pdf_per_doc(
    documents_by_projet, pdf_paths: dict[int, Path]
) -> tuple[str, str, bytes]:
    documents = _grouped_by_type(documents_by_projet)

    if len(documents) == 1:
        document = documents[0]
        pdf_content = pdf_paths[document.pk].read_bytes()
        logger.info(f"#1 {document} généré")
        return document.name, "application/pdf", pdf_content

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            zip_file.write(str(pdf_paths[document.pk]), arcname=document.name)
            logger.info(f"#{i} {document} généré")
    date_str = timezone.now().strftime("%d-%m-%Y")
    return f"export turgot {date_str}.zip", "application/zip", zip_buffer.getvalue()


def _build_single_merged_pdf(
    documents_by_projet, document_type, pdf_paths: dict[int, Path]
) -> tuple[str, str, bytes]:
    documents = _grouped_by_projet(documents_by_projet)
    merged = _merge_pdfs_from_paths(_pdf_paths(documents, pdf_paths))
    date_str = timezone.now().strftime("%d-%m-%Y")
    if document_type == ARRETE_ET_LETTRE:
        doc_type_fr = "lettres et arrêtés"
    else:
        doc_type_fr = GeneratedDocument.Type(document_type).short_name.lower()
    filename = f"export {doc_type_fr} turgot {date_str}.pdf"
    return filename, "application/pdf", merged


def _build_one_pdf_per_project(
    documents_by_projet, pdf_paths: dict[int, Path]
) -> tuple[str, str, bytes]:
    if len(documents_by_projet) == 1:
        documents = documents_by_projet[0]
        merged = _merge_pdfs_from_paths(_pdf_paths(documents, pdf_paths))
        date_str = timezone.now().strftime("%d-%m-%Y")
        dossier = documents[0].enveloppe_projet.dossier_ds
        ds_number = dossier.ds_number
        raison_sociale = slugify(dossier.ds_demandeur.raison_sociale)
        filename = f"lettre et arrêté - {ds_number} - {raison_sociale} - {date_str}.pdf"
        return filename, "application/pdf", merged

    date_str = timezone.now().strftime("%d-%m-%Y")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for documents in documents_by_projet:
            merged = _merge_pdfs_from_paths(_pdf_paths(documents, pdf_paths))
            dossier = documents[0].enveloppe_projet.dossier_ds
            ds_number = dossier.ds_number
            raison_sociale = slugify(dossier.ds_demandeur.raison_sociale)
            filename = f"lettre et arrêté - {ds_number} - {raison_sociale}.pdf"
            zip_file.writestr(filename, merged)
    return (
        f"export turgot {date_str}.zip",
        "application/zip",
        zip_buffer.getvalue(),
    )


def _build_grouped_merged_pdf(
    documents_by_projet, pdf_paths: dict[int, Path]
) -> tuple[str, str, bytes]:
    documents = _grouped_by_projet(documents_by_projet)
    merged = _merge_pdfs_from_paths(_pdf_paths(documents, pdf_paths))
    date_str = timezone.now().strftime("%d-%m-%Y")
    filename = f"export turgot {date_str}.pdf"
    return filename, "application/pdf", merged


def _grouped_by_projet(documents_by_projet) -> list[GeneratedDocument]:
    return [document for documents in documents_by_projet for document in documents]


def _grouped_by_type(documents_by_projet) -> list[GeneratedDocument]:
    return [document for column in zip(*documents_by_projet) for document in column]


def _pdf_paths(documents, pdf_paths: dict[int, Path]) -> list[Path]:
    return [pdf_paths[document.pk] for document in documents]


def _merge_pdfs_from_paths(paths: list[Path]) -> bytes:
    pdf = Pdf.new()
    for path in paths:
        src = Pdf.open(str(path))
        pdf.pages.extend(src.pages)
    output = io.BytesIO()
    pdf.save(output)
    return output.getvalue()


def upload_export_and_get_url(filename: str, content_type: str, body: bytes) -> str:
    key = f"{EXPORT_PREFIX}/{uuid.uuid4().hex}/{filename}"
    default_storage.save(key, ContentFile(body))
    try:
        return default_storage.url(
            key,
            parameters={
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
                "ResponseContentType": content_type,
            },
            expire=EXPORT_URL_TTL,
        )
    except TypeError:
        # Non-S3 backends (e.g. InMemoryStorage in tests) don't accept the
        # presign kwargs; fall back to the plain url.
        return default_storage.url(key)

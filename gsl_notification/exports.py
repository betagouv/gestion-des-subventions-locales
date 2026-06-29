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

from gsl_notification.forms import (
    ARRETE_ET_LETTRE,
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
)
from gsl_notification.utils import (
    count_pdf_pages,
    generate_pdf_pass1,
    generate_pdf_pass2,
)
from gsl_projet.constants import ARRETE

logger = logging.getLogger(__name__)

EXPORT_PREFIX = "tmp/notifications/exports"
EXPORT_URL_TTL = 900  # 15 minutes


def build_export(job) -> tuple[str, str, bytes]:
    from gsl_notification.models import ExportJob
    from gsl_programmation.models import ProgrammationProjet

    pk_to_pp = {
        pp.pk: pp
        for pp in ProgrammationProjet.objects.filter(pk__in=job.pp_ids).select_related(
            "arrete__modele",
            "lettre_notification__modele",
            "dotation_projet__projet__dossier_ds__ds_demandeur",
        )
    }
    pps = [pk_to_pp[pk] for pk in job.pp_ids]
    documents = [getattr(pp, attr) for attr in job.attr_names for pp in pps]
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
            pps, job.attr_names, job.export_format, job.document_type, pdf_paths
        )


def _render_pdfs_to_disk(job, documents, tmp_path: Path) -> dict[int, Path]:
    from gsl_notification.models import ExportJob

    if job.with_qr_code:
        ExportJob.objects.filter(pk=job.pk).update(
            step=1, processed=0, updated_at=timezone.now()
        )
        page_counts: dict[str, int] = {}
        for doc in documents:
            pdf = generate_pdf_pass1(doc)
            page_counts[f"{type(doc).__name__}_{doc.pk}"] = count_pdf_pages(pdf)
            ExportJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1, updated_at=timezone.now()
            )

        ExportJob.objects.filter(pk=job.pk).update(
            step=2, processed=0, updated_at=timezone.now()
        )
        pdf_paths: dict[str, Path] = {}
        for doc in documents:
            key = f"{type(doc).__name__}_{doc.pk}"
            pdf = generate_pdf_pass2(doc, page_counts[key])
            path = tmp_path / f"{key}.pdf"
            path.write_bytes(pdf)
            pdf_paths[key] = path
            ExportJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1, updated_at=timezone.now()
            )
    else:
        ExportJob.objects.filter(pk=job.pk).update(
            step=1, processed=0, updated_at=timezone.now()
        )
        pdf_paths = {}
        for doc in documents:
            key = f"{type(doc).__name__}_{doc.pk}"
            pdf = generate_pdf_pass1(doc)
            path = tmp_path / f"{key}.pdf"
            path.write_bytes(pdf)
            pdf_paths[key] = path
            ExportJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1, updated_at=timezone.now()
            )

    return pdf_paths


def _assemble_export(
    pps, attrs, export_format, document_type, pdf_paths: dict[str, Path]
) -> tuple[str, str, bytes]:
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL:
        return _build_single_merged_pdf(pps, attrs, document_type, pdf_paths)
    if export_format == EXPORT_FORMAT_ONE_PDF_PER_PROJECT:
        return _build_one_pdf_per_project(pps, attrs, pdf_paths)
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED:
        return _build_grouped_merged_pdf(pps, attrs, pdf_paths)
    return _build_one_pdf_per_doc(pps, attrs, pdf_paths)


def _build_one_pdf_per_doc(
    programmation_projets, attrs, pdf_paths: dict[str, Path]
) -> tuple[str, str, bytes]:
    documents = [
        doc
        for attr in attrs
        for doc in (getattr(pp, attr) for pp in programmation_projets)
    ]

    if len(documents) == 1:
        document = documents[0]
        key = f"{type(document).__name__}_{document.pk}"
        pdf_content = pdf_paths[key].read_bytes()
        logger.info(f"#1 {document} généré")
        return document.name, "application/pdf", pdf_content

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            key = f"{type(document).__name__}_{document.pk}"
            zip_file.write(str(pdf_paths[key]), arcname=document.name)
            logger.info(f"#{i} {document} généré")
    date_str = timezone.now().strftime("%d-%m-%Y")
    return f"export turgot {date_str}.zip", "application/zip", zip_buffer.getvalue()


def _build_single_merged_pdf(
    programmation_projets,
    attrs,
    document_type,
    pdf_paths: dict[str, Path],
) -> tuple[str, str, bytes]:
    paths = []
    for pp in programmation_projets:
        for attr in attrs:
            doc = getattr(pp, attr)
            paths.append(pdf_paths[f"{type(doc).__name__}_{doc.pk}"])
    merged = _merge_pdfs_from_paths(paths)
    date_str = timezone.now().strftime("%d-%m-%Y")
    if document_type == ARRETE:
        doc_type_fr = "arrêté"
    elif document_type == ARRETE_ET_LETTRE:
        doc_type_fr = "lettres et arrêtés"
    else:
        doc_type_fr = "lettre"
    filename = f"export {doc_type_fr} turgot {date_str}.pdf"
    return filename, "application/pdf", merged


def _build_one_pdf_per_project(
    programmation_projets, attrs, pdf_paths: dict[str, Path]
) -> tuple[str, str, bytes]:
    if len(programmation_projets) == 1:
        pp = programmation_projets[0]
        paths = [
            pdf_paths[f"{type(getattr(pp, attr)).__name__}_{getattr(pp, attr).pk}"]
            for attr in attrs
        ]
        merged = _merge_pdfs_from_paths(paths)
        date_str = timezone.now().strftime("%d-%m-%Y")
        ds_number = pp.dossier.ds_number
        raison_sociale = slugify(pp.dossier.ds_demandeur.raison_sociale)
        filename = f"lettre et arrêté - {ds_number} - {raison_sociale} - {date_str}.pdf"
        return filename, "application/pdf", merged

    date_str = timezone.now().strftime("%d-%m-%Y")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for pp in programmation_projets:
            paths = [
                pdf_paths[f"{type(getattr(pp, attr)).__name__}_{getattr(pp, attr).pk}"]
                for attr in attrs
            ]
            merged = _merge_pdfs_from_paths(paths)
            ds_number = pp.dossier.ds_number
            raison_sociale = slugify(pp.dossier.ds_demandeur.raison_sociale)
            filename = f"lettre et arrêté - {ds_number} - {raison_sociale}.pdf"
            zip_file.writestr(filename, merged)
    return (
        f"export turgot {date_str}.zip",
        "application/zip",
        zip_buffer.getvalue(),
    )


def _build_grouped_merged_pdf(
    programmation_projets, attrs, pdf_paths: dict[str, Path]
) -> tuple[str, str, bytes]:
    paths = []
    for pp in programmation_projets:
        for attr in attrs:
            doc = getattr(pp, attr)
            paths.append(pdf_paths[f"{type(doc).__name__}_{doc.pk}"])
    merged = _merge_pdfs_from_paths(paths)
    date_str = timezone.now().strftime("%d-%m-%Y")
    filename = f"export turgot {date_str}.pdf"
    return filename, "application/pdf", merged


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

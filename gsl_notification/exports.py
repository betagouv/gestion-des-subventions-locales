import io
import logging
import uuid
import zipfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import slugify
from pikepdf import Pdf

from gsl_notification.forms import (
    ARRETE_ET_LETTRE,
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
)
from gsl_notification.utils import generate_pdf_for_generated_document
from gsl_projet.constants import ARRETE

logger = logging.getLogger(__name__)

EXPORT_PREFIX = "tmp/notifications/exports"
EXPORT_URL_TTL = 900  # 15 minutes


def build_export(
    programmation_projets, attrs, export_format, document_type, *, with_qr_code=True
) -> tuple[str, str, bytes]:
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL:
        return _build_single_merged_pdf(
            programmation_projets, attrs, document_type, with_qr_code=with_qr_code
        )
    if export_format == EXPORT_FORMAT_ONE_PDF_PER_PROJECT:
        return _build_one_pdf_per_project(
            programmation_projets, attrs, with_qr_code=with_qr_code
        )
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED:
        return _build_grouped_merged_pdf(
            programmation_projets, attrs, with_qr_code=with_qr_code
        )
    return _build_one_pdf_per_doc(
        programmation_projets, attrs, with_qr_code=with_qr_code
    )


def _build_one_pdf_per_doc(
    programmation_projets, attrs, *, with_qr_code=True
) -> tuple[str, str, bytes]:
    documents = [
        doc
        for attr in attrs
        for doc in (getattr(pp, attr) for pp in programmation_projets)
    ]

    if len(documents) == 1:
        document = documents[0]
        pdf_content = generate_pdf_for_generated_document(
            document, with_qr_code=with_qr_code
        )
        logger.info(f"#1 {document} généré")
        return document.name, "application/pdf", pdf_content

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            pdf_content = generate_pdf_for_generated_document(
                document, with_qr_code=with_qr_code
            )
            zip_file.writestr(f"{document.name}", pdf_content)
            logger.info(f"#{i} {document} généré")
    date_str = timezone.now().strftime("%d-%m-%Y")
    return f"export turgot {date_str}.zip", "application/zip", zip_buffer.getvalue()


def _build_single_merged_pdf(
    programmation_projets, attrs, document_type, *, with_qr_code=True
) -> tuple[str, str, bytes]:
    pdf_bytes_list = []
    for pp in programmation_projets:
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(
                    getattr(pp, attr), with_qr_code=with_qr_code
                )
            )
    merged = _merge_pdfs_bytes(pdf_bytes_list)
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
    programmation_projets, attrs, *, with_qr_code=True
) -> tuple[str, str, bytes]:
    if len(programmation_projets) == 1:
        pp = programmation_projets[0]
        pdf_bytes_list = [
            generate_pdf_for_generated_document(
                getattr(pp, attr), with_qr_code=with_qr_code
            )
            for attr in attrs
        ]
        merged = _merge_pdfs_bytes(pdf_bytes_list)
        date_str = timezone.now().strftime("%d-%m-%Y")
        ds_number = pp.dossier.ds_number
        raison_sociale = slugify(pp.dossier.ds_demandeur.raison_sociale)
        filename = f"lettre et arrêté - {ds_number} - {raison_sociale} - {date_str}.pdf"
        return filename, "application/pdf", merged

    date_str = timezone.now().strftime("%d-%m-%Y")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for pp in programmation_projets:
            project_pdfs = [
                generate_pdf_for_generated_document(
                    getattr(pp, attr), with_qr_code=with_qr_code
                )
                for attr in attrs
            ]
            merged = _merge_pdfs_bytes(project_pdfs)
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
    programmation_projets, attrs, *, with_qr_code=True
) -> tuple[str, str, bytes]:
    pdf_bytes_list = []
    for pp in programmation_projets:
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(
                    getattr(pp, attr), with_qr_code=with_qr_code
                )
            )
    merged = _merge_pdfs_bytes(pdf_bytes_list)
    date_str = timezone.now().strftime("%d-%m-%Y")
    filename = f"export turgot {date_str}.pdf"
    return filename, "application/pdf", merged


def _merge_pdfs_bytes(pdf_bytes_list: list[bytes]) -> bytes:
    pdf = Pdf.new()
    for pdf_bytes in pdf_bytes_list:
        src = Pdf.open(io.BytesIO(pdf_bytes))
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

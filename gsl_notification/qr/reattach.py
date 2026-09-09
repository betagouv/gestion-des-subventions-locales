"""
Business logic for reattaching a scanned signed PDF to the matching
ProgrammationProjet(s), decoded from per-page GSL QR codes.

`extract_documents()` reads and matches, `replace_documents()` writes.
`reattach_signed_docs()` composes them, and is what the CLI command in
`gsl_notification/management/commands/reattach_signed_doc.py` and the web
import flow (`gsl_notification/tasks.py`) both call.
"""

import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator

from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import QuerySet
from pikepdf import Pdf

from gsl.projet.constants import ARRETE, LETTRE
from gsl_core.models import Collegue
from gsl_notification.models import UPLOADED_DOCUMENTS, UploadedDocument
from gsl_programmation.models import ProgrammationProjet

from .codec import iter_decoded_pages
from .mask import mask_qr_on_last_page

DOCUMENT_TYPE_ORDER = {LETTRE: 0, ARRETE: 1}

# Built by asking each UploadedDocument subclass which QR document types it is
# the target of, through `reattach_source_document_types` (see models.py).
_TARGET_MODEL_BY_DOCUMENT_TYPE: dict[str, type[UploadedDocument]] = {
    document_type: model
    for model in UPLOADED_DOCUMENTS.values()
    for document_type in model.reattach_source_document_types
}


@dataclass(frozen=True)
class ScannedPage:
    file_index: int
    scan_index: int
    doc_type: str
    claimed_page: int
    bbox: tuple[float, float, float, float] | None
    image_height_px: int | None


@dataclass(frozen=True)
class DeclaredDocument:
    """The document a scanned page says it belongs to, before any lookup.

    Pages sharing one become a single stored document, which is why the target
    model is part of it: an arrêté page and a lettre page of the same projet
    merge, a lettre de refus page of that same projet does not.
    """

    ds_number: int
    dotation: str
    target_model: type[UploadedDocument]


@dataclass(frozen=True)
class ExtractedDocument:
    declared: DeclaredDocument
    programmation_projet_id: int
    pages: tuple[ScannedPage, ...]


@dataclass(frozen=True)
class DecodeStarted:
    total_pages: int


@dataclass(frozen=True)
class PageDecoded:
    scan_page: int  # 1-based
    qr_found: bool
    file: str | None = None  # name of the source file the page belongs to


@dataclass(frozen=True)
class DocumentMatched:
    document: ExtractedDocument


@dataclass(frozen=True)
class MatchFailed:
    declared: DeclaredDocument
    error: str


@dataclass(frozen=True)
class DocumentAttached:
    document: ExtractedDocument
    stored: UploadedDocument


ExtractionEvent = DecodeStarted | PageDecoded | DocumentMatched | MatchFailed

ReattachEvent = DecodeStarted | PageDecoded | DocumentAttached | MatchFailed


def reattach_signed_docs(
    pdfs: list[File],
    user: Collegue,
    programmation_projets: QuerySet[ProgrammationProjet],
    remove_qr_code: bool = True,
) -> Iterator[ReattachEvent]:
    """Extract every document from the batch, then store each one, streaming
    events.

    Side effects (DB writes, file storage) happen lazily as the caller
    iterates. Callers must drain the generator.

    `programmation_projets` is the queryset a document is looked up in: the web
    flow scopes it to the importer's perimetre, the operator CLI passes them
    all. `user` is recorded as the author of every stored document.

    When `remove_qr_code` is True (the default), the GSL QR code is masked off
    each stored page; set it False to keep the QR visible on the stored file.
    """
    documents = []
    for event in extract_documents(pdfs, programmation_projets):
        if isinstance(event, DocumentMatched):
            documents.append(event.document)
        else:
            yield event

    yield from replace_documents(documents, pdfs, user, remove_qr_code)


def extract_documents(
    pdfs: list[File],
    programmation_projets: QuerySet[ProgrammationProjet],
) -> Iterator[ExtractionEvent]:
    """Decode every page, gather the pages of each declared document across the
    whole batch, and match it to its ProgrammationProjet — without writing
    anything.

    A named `pdf` (`ContentFile(..., name=...)`, or the `UploadedFile` a form
    hands over) has its name reported on every page event, so the agent knows
    which upload a faulty page came from.

    Writing nothing is what lets a caller take in the whole batch before
    committing to any of it: a scan carrying pages it should not touch can be
    refused as a whole, rather than half-attached before the problem shows up.
    """
    scanned_pages_by_document: dict[DeclaredDocument, list[ScannedPage]] = defaultdict(
        list
    )
    for file_index, pdf in enumerate(pdfs):
        pdf_bytes = _read(pdf)
        with Pdf.open(io.BytesIO(pdf_bytes)) as src:
            total_pages = len(src.pages)
        yield DecodeStarted(total_pages=total_pages)

        for scan_index, hit in enumerate(iter_decoded_pages(pdf_bytes)):
            if hit is not None:
                target_model = _TARGET_MODEL_BY_DOCUMENT_TYPE[hit.payload.document_type]
                declared = DeclaredDocument(
                    ds_number=hit.payload.ds_number,
                    dotation=hit.payload.dotation,
                    target_model=target_model,
                )
                scanned_pages_by_document[declared].append(
                    ScannedPage(
                        file_index=file_index,
                        scan_index=scan_index,
                        doc_type=hit.payload.document_type,
                        claimed_page=hit.payload.page,
                        bbox=hit.bbox,
                        image_height_px=hit.image_height_px,
                    )
                )
            yield PageDecoded(
                scan_page=scan_index + 1, qr_found=hit is not None, file=pdf.name
            )

    for declared, pages in scanned_pages_by_document.items():
        pages.sort(
            key=lambda p: (DOCUMENT_TYPE_ORDER.get(p.doc_type, 99), p.claimed_page)
        )
        yield _match_document(declared, pages, programmation_projets)


def replace_documents(
    documents: list[ExtractedDocument],
    pdfs: list[File],
    user: Collegue,
    remove_qr_code: bool = True,
) -> Iterator[DocumentAttached]:
    """Assemble each document into a single PDF and store it on its
    ProgrammationProjet, deleting any existing document of the same kind — its
    stored file included.

    `pdfs` must be the batch `documents` were extracted from: a page locates
    itself by index into it.
    """
    if not documents:
        return

    pdf_bytes_list = [_read(pdf) for pdf in pdfs]
    srcs = [Pdf.open(io.BytesIO(pdf_bytes)) for pdf_bytes in pdf_bytes_list]
    try:
        for document in documents:
            uploaded = _assemble_pages(srcs, pdf_bytes_list, document, remove_qr_code)
            stored = _replace_uploaded_document(
                document.declared.target_model,
                document.programmation_projet_id,
                uploaded,
                user,
            )
            yield DocumentAttached(document=document, stored=stored)
    finally:
        for src in srcs:
            src.close()


def _read(pdf: File) -> bytes:
    # An UploadedFile a form has already validated sits at EOF.
    pdf.seek(0)
    return pdf.read()


def _match_document(
    declared, pages, programmation_projets
) -> DocumentMatched | MatchFailed:
    try:
        programmation_projet = programmation_projets.get(
            dotation_projet__projet__dossier_ds__ds_number=declared.ds_number,
            dotation_projet__dotation=declared.dotation,
        )
    except ProgrammationProjet.DoesNotExist:
        return MatchFailed(
            declared=declared, error="Aucun projet programmé correspondant."
        )
    except ProgrammationProjet.MultipleObjectsReturned:
        return MatchFailed(
            declared=declared,
            error="Plusieurs projets programmés correspondent "
            "(incohérence, à corriger manuellement).",
        )

    return DocumentMatched(
        document=ExtractedDocument(
            declared=declared,
            programmation_projet_id=programmation_projet.id,
            pages=tuple(pages),
        )
    )


def _replace_uploaded_document(target_model, programmation_projet_id, uploaded, user):
    with transaction.atomic():
        existing = target_model.objects.filter(
            programmation_projet_id=programmation_projet_id
        ).first()
        if existing is not None:
            existing.delete()  # post_delete signal removes its stored file

        doc = target_model(
            programmation_projet_id=programmation_projet_id,
            created_by=user,
            file=uploaded,
        )
        doc.save()
        return doc


def _assemble_pages(srcs, pdf_bytes_list, document, remove_qr_code=True):
    declared = document.declared
    out = Pdf.new()
    for page in document.pages:
        out.pages.append(srcs[page.file_index].pages[page.scan_index])
        if remove_qr_code:
            mask_qr_on_last_page(
                out,
                page.bbox,
                page.image_height_px,
                pdf_bytes_list[page.file_index],
                page.scan_index,
            )
    buf = io.BytesIO()
    out.save(buf)
    buf.seek(0)
    prefix = declared.target_model.reattach_filename_prefix()
    return SimpleUploadedFile(
        name=f"{prefix}-{declared.ds_number}-{declared.dotation}.pdf",
        content=buf.read(),
        content_type="application/pdf",
    )

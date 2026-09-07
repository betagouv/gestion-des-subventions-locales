"""
Business logic for reattaching a scanned signed PDF to the matching
ProgrammationProjet(s), decoded from per-page GSL QR codes.

`reattach_signed_docs()` is the entry point: the CLI command in
`gsl_notification/management/commands/reattach_signed_doc.py` hands it one
file, the web import flow (`gsl_notification/tasks.py`) hands it the whole
batch.

Pages sharing `(ds_number, dotation)` *and* targeting the same document model
are grouped and reassembled (ordered by document type — lettre before
arrêté — then by the QR `page` field) into a single PDF before being
attached as the matching `UploadedDocument` subclass, replacing any existing
document of that kind for the project: `arrete`/`lettre` QR pages produce a
`LettreEtArreteSignes`, `refus` QR pages produce a `LettreRefusSignee`.

Grouping spans the *whole* job: `reattach_signed_docs()` decodes every
uploaded file first, then merges pages by `(ds_number, dotation, target_model)`
across all of them, so an arrêté file and a lettre file uploaded together end
up in a single `LettreEtArreteSignes` per project — while a lettre de refus
scanned alongside them is routed independently to its own `LettreRefusSignee`.
"""

import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator

from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from pikepdf import Pdf

from gsl.projet.constants import ARRETE, LETTRE
from gsl_core.models import Collegue
from gsl_notification.models import UPLOADED_DOCUMENTS, UploadedDocument
from gsl_programmation.models import ProgrammationProjet

from .codec import iter_decoded_pages
from .mask import mask_qr_on_last_page

DOCUMENT_TYPE_ORDER = {LETTRE: 0, ARRETE: 1}

# Which UploadedDocument subclass a QR document_type is reattached as, built
# from each model's `reattach_source_document_types` (see models.py):
# arrete/lettre pages are merged into a single LettreEtArreteSignes; refus
# pages (lettre de refus / classement sans suite) go to their own
# LettreRefusSignee, never mixed with the other two.
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


ExtractionEvent = DecodeStarted | PageDecoded | DocumentMatched | MatchFailed

ReattachEvent = DecodeStarted | PageDecoded | DocumentAttached | MatchFailed


def reattach_signed_docs(
    pdfs: list[File],
    user: Collegue,
    programmation_projets,
    remove_qr_code: bool = True,
) -> Iterator[ReattachEvent]:
    """Decode QRs across *all* uploaded files, merge pages sharing a
    `(ds_number, dotation, target_model)` into a single PDF, attach each
    group to its ProgrammationProjet as the matching document type, and
    stream events.

    `pdfs` are read once, up front. A named one (`ContentFile(..., name=...)`,
    or the `UploadedFile` a form hands over) has its name reported on any page
    that fails to decode, so the agent knows which upload to look at.

    Grouping spans the whole batch,
    so an arrêté file and a lettre file uploaded together produce one combined
    `LettreEtArreteSignes` per project (`_replace_uploaded_document` runs once
    per project and per target model, not once per file). A lettre de refus
    scanned in the same batch never merges with those pages — it targets a
    different model (`LettreRefusSignee`) and is grouped, reported, and
    attached independently, even for the same `(ds_number, dotation)`.

    Side effects (DB writes, file storage) happen lazily as the caller
    iterates. Callers must drain the generator.

    `programmation_projets` is the queryset a document is looked up in: the web
    flow scopes it to the importer's perimetre, the operator CLI passes them
    all. `user` is recorded as the author of every stored document.

    When `remove_qr_code` is True (the default), the GSL QR code is masked off
    each stored page; set it False to keep the QR visible on the stored file.
    """
    srcs: list[Pdf] = []
    pdf_bytes_list: list[bytes] = []
    try:
        scanned_pages_by_document: dict[DeclaredDocument, list[ScannedPage]] = (
            defaultdict(list)
        )
        for file_index, pdf in enumerate(pdfs):
            # An UploadedFile a form has already validated sits at EOF.
            pdf.seek(0)
            pdf_bytes = pdf.read()
            src = Pdf.open(io.BytesIO(pdf_bytes))
            srcs.append(src)
            pdf_bytes_list.append(pdf_bytes)
            yield DecodeStarted(total_pages=len(src.pages))

            for scan_index, hit in enumerate(iter_decoded_pages(pdf_bytes)):
                if hit is not None:
                    target_model = _TARGET_MODEL_BY_DOCUMENT_TYPE[
                        hit.payload.document_type
                    ]
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
            outcome = _match_document(declared, pages, programmation_projets)
            if isinstance(outcome, MatchFailed):
                yield outcome
                continue

            document = outcome.document
            uploaded = _assemble_pages(srcs, pdf_bytes_list, document, remove_qr_code)
            _replace_uploaded_document(
                document.declared.target_model,
                document.programmation_projet_id,
                uploaded,
                user,
            )
            yield DocumentAttached(document=document)
    finally:
        for src in srcs:
            src.close()


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

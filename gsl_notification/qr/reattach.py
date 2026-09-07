"""
Business logic for reattaching a scanned signed PDF to the matching
ProgrammationProjet(s), decoded from per-page GSL QR codes.

The CLI command in
`gsl_notification/management/commands/reattach_signed_doc.py` is a thin
wrapper around `reattach_signed_doc()`; the web import flow
(`gsl_notification/tasks.py`) calls `reattach_signed_docs()` with the bytes of
every uploaded file.

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
`reattach_signed_doc()` is a single-file wrapper kept for the operator CLI.
"""

import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator

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
class GroupReport:
    ds_number: int
    dotation: str
    programmation_projet_id: int | None
    target_document_type: str
    pages_by_doc_type: dict[str, list[int]]
    error: str | None


@dataclass(frozen=True)
class DecodeStarted:
    total_pages: int


@dataclass(frozen=True)
class PageDecoded:
    scan_page: int  # 1-based; emitted when a page yielded a valid QR
    file: str | None = None  # stem of the source file the page belongs to


@dataclass(frozen=True)
class UnreadablePage:
    scan_page: int  # 1-based
    file: str | None = None  # stem of the source file the page belongs to


@dataclass(frozen=True)
class GroupAttached:
    report: GroupReport


@dataclass(frozen=True)
class GroupFailed:
    report: GroupReport


ReattachEvent = (
    DecodeStarted | PageDecoded | UnreadablePage | GroupAttached | GroupFailed
)


def reattach_signed_doc(
    pdf_bytes: bytes,
    user: Collegue,
    name_stem: str = "signed",
    restrict_to_user_perimetre: bool = False,
    remove_qr_code: bool = True,
) -> Iterator[ReattachEvent]:
    """Single-file wrapper around `reattach_signed_docs` (used by the CLI).

    See `reattach_signed_docs` for the semantics; this entry point keeps the
    operator command and any single-PDF caller unchanged.
    """
    yield from reattach_signed_docs(
        [(name_stem, pdf_bytes)],
        user,
        restrict_to_user_perimetre=restrict_to_user_perimetre,
        remove_qr_code=remove_qr_code,
    )


@dataclass(frozen=True)
class ScannedPage:
    file_index: int
    scan_index: int
    doc_type: str
    claimed_page: int
    bbox: tuple[float, float, float, float] | None
    image_height_px: int | None


def reattach_signed_docs(
    files: list[tuple[str, bytes]],
    user: Collegue,
    restrict_to_user_perimetre: bool = False,
    remove_qr_code: bool = True,
) -> Iterator[ReattachEvent]:
    """Decode QRs across *all* uploaded files, merge pages sharing a
    `(ds_number, dotation, target_model)` into a single PDF, attach each
    group to its ProgrammationProjet as the matching document type, and
    stream events.

    `files` is a list of `(stem, pdf_bytes)`. Grouping spans the whole list,
    so an arrêté file and a lettre file uploaded together produce one combined
    `LettreEtArreteSignes` per project (`_replace_uploaded_document` runs once
    per project and per target model, not once per file). A lettre de refus
    scanned in the same batch never merges with those pages — it targets a
    different model (`LettreRefusSignee`) and is grouped, reported, and
    attached independently, even for the same `(ds_number, dotation)`.

    Side effects (DB writes, file storage) happen lazily as the caller
    iterates. Callers must drain the generator.

    When `restrict_to_user_perimetre` is True, matching is scoped to the
    ProgrammationProjet visible to `user` (used by the web upload flow); the
    operator CLI leaves it False to keep matching global.

    When `remove_qr_code` is True (the default), the GSL QR code is masked off
    each stored page; set it False to keep the QR visible on the stored file.
    """
    srcs: list[Pdf] = []
    pdf_bytes_list: list[bytes] = []
    try:
        groups: dict[tuple[int, str, type[UploadedDocument]], list[ScannedPage]] = (
            defaultdict(list)
        )
        for file_index, (stem, pdf_bytes) in enumerate(files):
            src = Pdf.open(io.BytesIO(pdf_bytes))
            srcs.append(src)
            pdf_bytes_list.append(pdf_bytes)
            yield DecodeStarted(total_pages=len(src.pages))

            for scan_index, hit in enumerate(iter_decoded_pages(pdf_bytes)):
                scan_page = scan_index + 1
                if hit is None:
                    yield UnreadablePage(scan_page=scan_page, file=stem)
                    continue
                target_model = _TARGET_MODEL_BY_DOCUMENT_TYPE[hit.payload.document_type]
                groups[
                    (hit.payload.ds_number, hit.payload.dotation, target_model)
                ].append(
                    ScannedPage(
                        file_index=file_index,
                        scan_index=scan_index,
                        doc_type=hit.payload.document_type,
                        claimed_page=hit.payload.page,
                        bbox=hit.bbox,
                        image_height_px=hit.image_height_px,
                    )
                )
                yield PageDecoded(scan_page=scan_page, file=stem)

        for (ds, dot, target_model), pages in groups.items():
            pages.sort(
                key=lambda p: (DOCUMENT_TYPE_ORDER.get(p.doc_type, 99), p.claimed_page)
            )
            report = _attach_group(
                srcs,
                pdf_bytes_list,
                ds,
                dot,
                target_model,
                pages,
                user,
                restrict_to_user_perimetre,
                remove_qr_code,
            )
            if report.error is None:
                yield GroupAttached(report=report)
            else:
                yield GroupFailed(report=report)
    finally:
        for src in srcs:
            src.close()


def _attach_group(
    srcs,
    pdf_bytes_list,
    ds,
    dot,
    target_model,
    pages,
    user,
    restrict_to_user_perimetre=False,
    remove_qr_code=True,
) -> GroupReport:
    by_type: dict[str, list[int]] = defaultdict(list)
    for page in pages:
        by_type[page.doc_type].append(page.scan_index + 1)
    for doc_type in by_type:
        by_type[doc_type].sort()
    pages_by_doc_type = dict(by_type)
    target_document_type = target_model.document_type

    # Scope matching to the importer's perimetre for the web flow; the operator
    # CLI keeps the global queryset. Out-of-perimetre groups simply miss the
    # lookup and fall through to the DoesNotExist branch below.
    queryset = (
        ProgrammationProjet.objects.visible_to_user(user)
        if restrict_to_user_perimetre
        else ProgrammationProjet.objects
    )

    try:
        pp = queryset.get(
            dotation_projet__projet__dossier_ds__ds_number=ds,
            dotation_projet__dotation=dot,
        )
    except ProgrammationProjet.DoesNotExist:
        return GroupReport(
            ds_number=ds,
            dotation=dot,
            programmation_projet_id=None,
            target_document_type=target_document_type,
            pages_by_doc_type=pages_by_doc_type,
            error="Aucun projet programmé correspondant.",
        )
    except ProgrammationProjet.MultipleObjectsReturned:
        return GroupReport(
            ds_number=ds,
            dotation=dot,
            programmation_projet_id=None,
            target_document_type=target_document_type,
            pages_by_doc_type=pages_by_doc_type,
            error="Plusieurs projets programmés correspondent "
            "(incohérence, à corriger manuellement).",
        )

    uploaded = _build_group_pdf(
        srcs, pages, ds, dot, target_model, pdf_bytes_list, remove_qr_code
    )
    _replace_uploaded_document(target_model, pp, uploaded, user)

    return GroupReport(
        ds_number=ds,
        dotation=dot,
        programmation_projet_id=pp.id,
        target_document_type=target_document_type,
        pages_by_doc_type=pages_by_doc_type,
        error=None,
    )


def _replace_uploaded_document(target_model, pp, uploaded, user):
    with transaction.atomic():
        existing = target_model.objects.filter(programmation_projet=pp).first()
        if existing is not None:
            existing.delete()  # post_delete signal removes its stored file

        doc = target_model(
            programmation_projet=pp,
            created_by=user,
            file=uploaded,
        )
        doc.save()


def _build_group_pdf(
    srcs, pages, ds, dot, target_model, pdf_bytes_list, remove_qr_code=True
):
    out = Pdf.new()
    for page in pages:
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
    return SimpleUploadedFile(
        name=f"{target_model.reattach_filename_prefix()}-{ds}-{dot}.pdf",
        content=buf.read(),
        content_type="application/pdf",
    )

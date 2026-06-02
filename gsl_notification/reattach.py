"""
Business logic for reattaching a scanned signed PDF to the matching
ProgrammationProjet(s), decoded from per-page GSL QR codes.

The CLI command in
`gsl_notification/management/commands/reattach_signed_doc.py` is a thin
wrapper around `reattach_signed_doc()`; a future upload view can call the
same entry point with bytes from an `UploadedFile`.

Pages sharing `(ds_number, dotation)` are grouped and reassembled (ordered
by document type — lettre before arrêté — then by the QR `page` field)
into a single PDF before being attached as a `LettreEtArreteSignes`,
replacing any existing one.
"""

import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

import pikepdf
import pypdfium2 as pdfium
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from pikepdf import Page, Pdf
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from gsl_core.models import Collegue
from gsl_notification.models import LettreEtArreteSignes
from gsl_notification.qr import RENDER_SCALE, iter_decoded_pages
from gsl_notification.utils import (
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import ARRETE, LETTRE

_DOCUMENT_TYPE_ORDER = {LETTRE: 0, ARRETE: 1}


@dataclass(frozen=True)
class GroupReport:
    ds_number: int
    dotation: str
    programmation_projet_id: int | None
    pages_by_doc_type: dict[str, list[int]]
    error: str | None


@dataclass(frozen=True)
class DecodeStarted:
    total_pages: int


@dataclass(frozen=True)
class PageDecoded:
    scan_page: int  # 1-based; emitted when a page yielded a valid QR


@dataclass(frozen=True)
class UnreadablePage:
    scan_page: int  # 1-based


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
    pdf_source: Path | bytes | BinaryIO,
    user: Collegue,
    name_stem: str = "signed",
    restrict_to_user_perimetre: bool = False,
    remove_qr_code: bool = True,
) -> Iterator[ReattachEvent]:
    """Decode QRs from a scanned signed PDF, attach each group to its
    ProgrammationProjet as a LettreEtArreteSignes, and stream events.

    Side effects (DB writes, file storage) happen lazily as the caller
    iterates. Callers must drain the generator.

    When `restrict_to_user_perimetre` is True, matching is scoped to the
    ProgrammationProjet visible to `user` (used by the web upload flow); the
    operator CLI leaves it False to keep matching global.

    When `remove_qr_code` is True (the default), the GSL QR code is masked off
    each stored page; set it False to keep the QR visible on the stored file.
    """
    pdf_bytes = _read_to_bytes(pdf_source)

    src = Pdf.open(io.BytesIO(pdf_bytes))
    try:
        yield DecodeStarted(total_pages=len(src.pages))

        groups: dict[
            tuple[int, str],
            list[
                tuple[
                    int, str, int, tuple[float, float, float, float] | None, int | None
                ]
            ],
        ] = defaultdict(list)
        for scan_idx, hit in enumerate(iter_decoded_pages(pdf_bytes)):
            scan_page = scan_idx + 1
            if hit is None:
                yield UnreadablePage(scan_page=scan_page)
                continue
            groups[(hit.payload.ds_number, hit.payload.dotation)].append(
                (
                    scan_idx,
                    hit.payload.document_type,
                    hit.payload.page,
                    hit.bbox,
                    hit.image_height_px,
                )
            )
            yield PageDecoded(scan_page=scan_page)

        for (ds, dot), entries in groups.items():
            entries.sort(key=lambda e: (_DOCUMENT_TYPE_ORDER.get(e[1], 99), e[2]))
            report = _attach_group(
                src,
                pdf_bytes,
                ds,
                dot,
                entries,
                user,
                name_stem,
                restrict_to_user_perimetre,
                remove_qr_code,
            )
            if report.error is None:
                yield GroupAttached(report=report)
            else:
                yield GroupFailed(report=report)
    finally:
        src.close()


def _read_to_bytes(pdf_source: Path | bytes | BinaryIO) -> bytes:
    if isinstance(pdf_source, Path):
        return pdf_source.read_bytes()
    if isinstance(pdf_source, bytes):
        return pdf_source
    return pdf_source.read()


def _group_pages(per_page):
    groups: dict[
        tuple[int, str],
        list[
            tuple[int, str, int, tuple[float, float, float, float] | None, int | None]
        ],
    ] = defaultdict(list)
    unreadable: list[int] = []
    for scan_idx, hit in enumerate(per_page):
        if hit is None:
            unreadable.append(scan_idx + 1)
            continue
        groups[(hit.payload.ds_number, hit.payload.dotation)].append(
            (
                scan_idx,
                hit.payload.document_type,
                hit.payload.page,
                hit.bbox,
                hit.image_height_px,
            )
        )
    return groups, unreadable


def _attach_group(
    src,
    pdf_bytes,
    ds,
    dot,
    entries,
    user,
    name_stem,
    restrict_to_user_perimetre=False,
    remove_qr_code=True,
) -> GroupReport:
    by_type: dict[str, list[int]] = defaultdict(list)
    for scan_idx, doc_type, *_ in entries:
        by_type[doc_type].append(scan_idx + 1)
    for doc_type in by_type:
        by_type[doc_type].sort()
    pages_by_doc_type = dict(by_type)

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
            pages_by_doc_type=pages_by_doc_type,
            error="no matching ProgrammationProjet",
        )
    except ProgrammationProjet.MultipleObjectsReturned:
        return GroupReport(
            ds_number=ds,
            dotation=dot,
            programmation_projet_id=None,
            pages_by_doc_type=pages_by_doc_type,
            error="multiple ProgrammationProjet (data inconsistency, fix manually)",
        )

    uploaded = _build_group_pdf(
        src, entries, name_stem, ds, dot, pdf_bytes, remove_qr_code
    )
    _replace_lettre_et_arrete(pp, uploaded, user)

    return GroupReport(
        ds_number=ds,
        dotation=dot,
        programmation_projet_id=pp.id,
        pages_by_doc_type=pages_by_doc_type,
        error=None,
    )


def _replace_lettre_et_arrete(pp, uploaded, user):
    with transaction.atomic():
        existing = LettreEtArreteSignes.objects.filter(programmation_projet=pp).first()
        if existing is not None:
            existing.delete()  # post_delete signal removes its stored file

        doc = LettreEtArreteSignes(
            programmation_projet=pp,
            created_by=user,
            file=uploaded,
        )
        update_file_name_to_put_it_in_a_programmation_projet_folder(
            doc.file, pp.id, is_annexe=False
        )
        doc.save()


def _build_group_pdf(src, entries, stem, ds, dot, pdf_bytes, remove_qr_code=True):
    out = Pdf.new()
    for scan_idx, _, _, bbox_px, image_height_px in entries:
        out.pages.append(src.pages[scan_idx])
        if remove_qr_code:
            _mask_qr_on_last_page(out, bbox_px, image_height_px, pdf_bytes, scan_idx)
    buf = io.BytesIO()
    out.save(buf)
    buf.seek(0)
    return SimpleUploadedFile(
        name=f"{stem}_ds{ds}_{dot}.pdf",
        content=buf.read(),
        content_type="application/pdf",
    )


# Padding (in PDF points) applied around the detected QR bbox so a small
# scan misalignment cannot leak visible modules past the patch.
# 3 pt ≈ 1 mm; the CSS `@page` margin reserves much more around the QR,
# so this stays comfortably inside the page margin.
_QR_MASK_PADDING_PT = 3.0

# Width of the alpha feather around the patch, in PDF points. Keeps the
# transition between the patched area and the surrounding scan from showing
# a hard rectangular seam. The feather band sits entirely outside the QR
# bbox + padding, so it only blends with paper, not with QR modules.
_FEATHER_PT = 6.0

# Thickness of the candidate background swatches sampled around the QR,
# expressed as a fraction of the QR's longest side. ~0.3 gives enough pixels
# to average out scan noise without reaching far into nearby content.
_SWATCH_THICKNESS_RATIO = 0.3


def _mask_qr_on_last_page(out, bbox_px, image_height_px, pdf_bytes, page_index):
    """Cover the QR area on the most recently appended page with a textured patch.

    The mask uses raw PDF user-space coordinates (bottom-left origin, Y up).
    To make these coordinates meaningful regardless of any top-level CTM
    operations the page's content stream may have set (WeasyPrint, for
    example, applies a global Y-flip), we wrap the existing content in a
    `q ... Q` pair: that pushes the graphics state before any CTM
    modifications and pops it back to the page's default (identity) CTM
    before we draw.

    The patch itself is a small image XObject sampled from the scan's own
    background around the QR, with feathered alpha edges so the join blends
    in. Falls back to a solid white rectangle if no usable swatch can be
    sampled (e.g. QR pinned in a corner with no clean side).
    """
    if bbox_px is None or not image_height_px:
        return

    page = out.pages[-1]
    media_box = page.MediaBox
    page_height_pt = float(media_box[3]) - float(media_box[1])
    scale = page_height_pt / image_height_px

    x_px, y_px, w_px, h_px = bbox_px

    pikepdf_page = Page(page)
    # Save graphics state before any of the page's existing content runs,
    # so the matching `Q` we append after it resets the CTM to its default.
    pikepdf_page.contents_add(b"q\n", prepend=True)

    patch = _build_texture_patch(pdf_bytes, page_index, bbox_px)
    if patch is None:
        x_pt = x_px * scale - _QR_MASK_PADDING_PT
        w_pt = w_px * scale + 2 * _QR_MASK_PADDING_PT
        h_pt = h_px * scale + 2 * _QR_MASK_PADDING_PT
        y_pt = page_height_pt - (y_px + h_px) * scale - _QR_MASK_PADDING_PT
        overlay = (
            f"\nQ\nq 1 1 1 rg {x_pt:.3f} {y_pt:.3f} {w_pt:.3f} {h_pt:.3f} re f Q\n"
        ).encode("ascii")
    else:
        # The textured patch's opaque core covers bbox + _QR_MASK_PADDING_PT,
        # and the alpha feather extends a further _FEATHER_PT band on each
        # side. The PDF rectangle must match the full PIL image size so the
        # feather lands on paper, not on QR modules.
        outer_margin_pt = _QR_MASK_PADDING_PT + _FEATHER_PT
        x_pt = x_px * scale - outer_margin_pt
        w_pt = w_px * scale + 2 * outer_margin_pt
        h_pt = h_px * scale + 2 * outer_margin_pt
        y_pt = page_height_pt - (y_px + h_px) * scale - outer_margin_pt

        xobject = _make_image_xobject(out, patch)
        name = pikepdf_page.add_resource(
            xobject, pikepdf.Name.XObject, prefix="GslMask"
        )
        # `cm` here is `w 0 0 h x y` which scales the unit-square XObject up
        # to the patch size and translates it to the bbox origin (PDF y-up).
        overlay = (
            f"\nQ\nq {w_pt:.3f} 0 0 {h_pt:.3f} {x_pt:.3f} {y_pt:.3f} cm {name} Do Q\n"
        ).encode("ascii")
    pikepdf_page.contents_add(overlay, prepend=False)


def _build_texture_patch(pdf_bytes, page_index, bbox_px):
    """Return an RGBA PIL image to overlay on the QR area, or None.

    Re-rasterises the source page at the same scale as `decode_per_page` so
    the bbox pixel coordinates line up exactly. Picks the candidate side
    (above/below/left/right of the QR) with the lowest channel variance —
    the most uniform strip is the best stand-in for the surrounding paper.
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        image = pdf[page_index].render(scale=RENDER_SCALE).to_pil().convert("RGB")
    finally:
        pdf.close()

    img_w, img_h = image.size
    x, y, w, h = (int(round(v)) for v in bbox_px)
    if w <= 0 or h <= 0:
        return None

    longest = max(w, h)
    thickness = max(8, int(round(_SWATCH_THICKNESS_RATIO * longest)))
    pad_px = max(1, int(round(_QR_MASK_PADDING_PT * RENDER_SCALE)))
    feather_px = max(2, int(round(_FEATHER_PT * RENDER_SCALE)))

    target_w = w + 2 * (pad_px + feather_px)
    target_h = h + 2 * (pad_px + feather_px)

    outer_x0 = x - pad_px
    outer_y0 = y - pad_px
    outer_x1 = x + w + pad_px
    outer_y1 = y + h + pad_px
    candidate_boxes = (
        (outer_x0, outer_y0 - thickness, outer_x1, outer_y0),  # above
        (outer_x0, outer_y1, outer_x1, outer_y1 + thickness),  # below
        (outer_x0 - thickness, outer_y0, outer_x0, outer_y1),  # left
        (outer_x1, outer_y0, outer_x1 + thickness, outer_y1),  # right
    )

    best_swatch = None
    best_variance = None
    for x0, y0, x1, y1 in candidate_boxes:
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(img_w, x1), min(img_h, y1)
        if cx1 - cx0 < 4 or cy1 - cy0 < 4:
            continue
        crop = image.crop((cx0, cy0, cx1, cy1))
        variance = sum(ImageStat.Stat(crop).var)
        if best_variance is None or variance < best_variance:
            best_variance = variance
            best_swatch = crop

    if best_swatch is None:
        return None

    patch = _tile_to(best_swatch, target_w, target_h)
    patch = patch.filter(ImageFilter.GaussianBlur(radius=1.0))

    # Hard opaque core covering bbox + safety padding: alpha = 255 across
    # the whole QR area so no module bleeds through.
    core = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(core).rectangle(
        [feather_px, feather_px, target_w - feather_px, target_h - feather_px],
        fill=255,
    )
    # Gaussian-blurred copy provides the soft outward fade onto paper.
    blurred = core.filter(ImageFilter.GaussianBlur(radius=feather_px / 2))
    # Max-composite: the core pins alpha to 255 inside the bbox-pad zone;
    # outside it, the blurred copy tapers smoothly to 0.
    mask = ImageChops.lighter(core, blurred)

    patch = patch.convert("RGBA")
    patch.putalpha(mask)
    return patch


def _tile_to(swatch, target_w, target_h):
    sw_w, sw_h = swatch.size
    if sw_w >= target_w and sw_h >= target_h:
        return swatch.crop((0, 0, target_w, target_h))
    out = Image.new(swatch.mode, (target_w, target_h))
    for ty in range(0, target_h, sw_h):
        for tx in range(0, target_w, sw_w):
            out.paste(swatch, (tx, ty))
    return out


def _make_image_xobject(pdf, pil_image):
    """Embed `pil_image` (RGBA) as an Image XObject with a soft mask."""
    rgb = pil_image.convert("RGB")
    alpha = pil_image.split()[-1]

    image_stream = pdf.make_stream(rgb.tobytes())
    image_stream.Type = pikepdf.Name.XObject
    image_stream.Subtype = pikepdf.Name.Image
    image_stream.Width = pil_image.width
    image_stream.Height = pil_image.height
    image_stream.ColorSpace = pikepdf.Name.DeviceRGB
    image_stream.BitsPerComponent = 8

    smask_stream = pdf.make_stream(alpha.tobytes())
    smask_stream.Type = pikepdf.Name.XObject
    smask_stream.Subtype = pikepdf.Name.Image
    smask_stream.Width = pil_image.width
    smask_stream.Height = pil_image.height
    smask_stream.ColorSpace = pikepdf.Name.DeviceGray
    smask_stream.BitsPerComponent = 8

    image_stream.SMask = smask_stream
    return image_stream


def _format_page_range(pages):
    if not pages:
        return ""
    if len(pages) == 1:
        return str(pages[0])
    if pages == list(range(pages[0], pages[-1] + 1)):
        return f"{pages[0]}–{pages[-1]}"
    return ", ".join(str(p) for p in pages)

"""
QR code utilities for the signed-document round-trip POC.

A small QR code is rendered at the bottom-left of every page of generated
documents (arrêté, lettre de notification). It encodes enough information
to reattach a scanned signed document to the right ProgrammationProjet.

Payload format (alphanumeric-mode compatible, colon-separated):

    GSL1:<ds_number>:<D|S>:<A|L>:<page>

Example: GSL1:123456:D:A:1

`GSL1` is a single token combining the prefix and format version (the
trailing digit reserves room for a future `GSL2`). The format only uses
characters allowed in QR alphanumeric mode (`0-9 A-Z` plus `:`), which
packs at 11 bits per 2 chars and keeps the QR sparse (likely version 1,
21×21 modules at error correction `"h"`). Dotation is encoded as `D`
(DETR) or `S` (DSIL); document type as `A` (arrete) or `L` (lettre).
"""

import base64
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

import segno

from gsl_projet.constants import ARRETE, DOTATION_DETR, DOTATION_DSIL, LETTRE

PAYLOAD_PREFIX = "GSL1"

# Scale used when rasterising pages for QR detection. Kept module-level so the
# texture-patch code in `reattach_signed_doc` can render at the exact same
# resolution and reuse the bbox coordinates without rescaling.
RENDER_SCALE = 200 / 72

_ALLOWED_DOTATIONS = (DOTATION_DETR, DOTATION_DSIL)
_ALLOWED_DOCUMENT_TYPES = (ARRETE, LETTRE)

_DOTATION_TO_CODE = {DOTATION_DETR: "D", DOTATION_DSIL: "S"}
_CODE_TO_DOTATION = {v: k for k, v in _DOTATION_TO_CODE.items()}

_DOCUMENT_TYPE_TO_CODE = {ARRETE: "A", LETTRE: "L"}
_CODE_TO_DOCUMENT_TYPE = {v: k for k, v in _DOCUMENT_TYPE_TO_CODE.items()}

_PAYLOAD_RE = re.compile(
    r"^GSL1:(?P<ds_number>\d+):(?P<dotation>[DS]):(?P<document_type>[AL]):(?P<page>\d+)$"
)


@dataclass(frozen=True)
class QrPayload:
    ds_number: int
    dotation: str
    document_type: str
    page: int


@dataclass(frozen=True)
class QrHit:
    """A successfully decoded GSL QR on a rendered page.

    `bbox` is the axis-aligned bounding box of the QR in image-pixel space
    (top-down), as `(x, y, width, height)`. Image dimensions are exposed so
    callers can map pixel coordinates back to PDF user space (which is
    bottom-up).
    """

    payload: QrPayload
    bbox: tuple[float, float, float, float]
    image_width_px: int
    image_height_px: int


def build_payload(ds_number: int, dotation: str, document_type: str, page: int) -> str:
    if dotation not in _ALLOWED_DOTATIONS:
        raise ValueError(f"Unknown dotation: {dotation!r}")
    if document_type not in _ALLOWED_DOCUMENT_TYPES:
        raise ValueError(f"Unknown document_type: {document_type!r}")
    if page < 1:
        raise ValueError(f"page must be >= 1, got {page}")
    return (
        f"{PAYLOAD_PREFIX}:{ds_number}"
        f":{_DOTATION_TO_CODE[dotation]}"
        f":{_DOCUMENT_TYPE_TO_CODE[document_type]}"
        f":{page}"
    )


def parse_payload(raw: str) -> QrPayload | None:
    """Return a QrPayload, or None if the string is not a valid GSL payload."""
    match = _PAYLOAD_RE.match(raw.strip())
    if match is None:
        return None
    return QrPayload(
        ds_number=int(match["ds_number"]),
        dotation=_CODE_TO_DOTATION[match["dotation"]],
        document_type=_CODE_TO_DOCUMENT_TYPE[match["document_type"]],
        page=int(match["page"]),
    )


def iter_decoded_pages(
    pdf_source: Path | bytes | BinaryIO,
) -> Iterator[QrHit | None]:
    """Yield one `QrHit | None` per page, in source order.

    Each yield = one page rasterised + QR-scanned. The caller controls
    pacing (and can interleave its own events between pages).
    """
    import pypdfium2 as pdfium
    import zxingcpp

    if isinstance(pdf_source, Path):
        pdf_bytes = pdf_source.read_bytes()
    elif isinstance(pdf_source, bytes):
        pdf_bytes = pdf_source
    else:
        pdf_bytes = pdf_source.read()

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for page in pdf:
            image = page.render(scale=RENDER_SCALE).to_pil()
            found: QrHit | None = None
            for r in zxingcpp.read_barcodes(image):
                payload = parse_payload(r.text)
                if payload is None:
                    continue
                found = QrHit(
                    payload=payload,
                    bbox=_axis_aligned_bbox(r.position),
                    image_width_px=image.width,
                    image_height_px=image.height,
                )
                break
            yield found
    finally:
        pdf.close()


def decode_per_page(
    pdf_source: Path | bytes | BinaryIO,
) -> list[QrHit | None]:
    """One entry per page (0-based index in the source PDF). None = no GSL QR found."""
    return list(iter_decoded_pages(pdf_source))


def _axis_aligned_bbox(position) -> tuple[float, float, float, float]:
    """Return `(x, y, width, height)` enclosing the four corners of a `zxingcpp.Position`."""
    corners = (
        position.top_left,
        position.top_right,
        position.bottom_left,
        position.bottom_right,
    )
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return (float(x_min), float(y_min), float(x_max - x_min), float(y_max - y_min))


def generate_qr_png_data_uri(payload: str, scale: int = 2, border: int = 1) -> str:
    """Return a base64 PNG data URI suitable for CSS `content: url(...)`."""
    qr = segno.make(payload, error="h")  # high error correction for print/scan
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"

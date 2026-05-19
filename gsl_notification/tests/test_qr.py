import base64
import io
from unittest.mock import patch

import pytest
from PIL import Image

from gsl_notification.qr import (
    QrPayload,
    build_payload,
    decode_per_page,
    generate_qr_png_data_uri,
    parse_payload,
)
from gsl_projet.constants import ARRETE, DOTATION_DETR, DOTATION_DSIL, LETTRE


def test_build_payload_format():
    assert build_payload(123456, DOTATION_DETR, ARRETE, 1) == "GSL1:123456:D:A:1"


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@pytest.mark.parametrize("document_type", [ARRETE, LETTRE])
def test_build_and_parse_roundtrip(dotation, document_type):
    payload = build_payload(987654, dotation, document_type, 3)
    assert parse_payload(payload) == QrPayload(
        ds_number=987654,
        dotation=dotation,
        document_type=document_type,
        page=3,
    )


def test_build_payload_rejects_bad_dotation():
    with pytest.raises(ValueError):
        build_payload(1, "ZZZZ", ARRETE, 1)


def test_build_payload_rejects_bad_document_type():
    with pytest.raises(ValueError):
        build_payload(1, DOTATION_DETR, "facture", 1)


def test_build_payload_rejects_bad_page():
    with pytest.raises(ValueError):
        build_payload(1, DOTATION_DETR, ARRETE, 0)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not a payload",
        "GSL2:1:D:A:1",  # wrong version prefix
        "GSL1:abc:D:A:1",  # non-numeric ds_number
        "GSL1:1:D:A",  # missing page
        "GSL1:1:X:A:1",  # bad dotation
    ],
)
def test_parse_payload_returns_none_on_invalid(raw):
    assert parse_payload(raw) is None


def test_parse_payload_tolerates_whitespace():
    assert parse_payload("  GSL1:42:S:L:2  \n") == QrPayload(
        ds_number=42,
        dotation=DOTATION_DSIL,
        document_type=LETTRE,
        page=2,
    )


def test_generate_qr_png_data_uri_is_a_valid_png():
    uri = generate_qr_png_data_uri("GSL1:1:D:A:1")
    assert uri.startswith("data:image/png;base64,")

    png_bytes = base64.b64decode(uri.split(",", 1)[1])
    image = Image.open(io.BytesIO(png_bytes))
    image.verify()
    assert image.format == "PNG"


# --- End-to-end round-trip: generate a PDF, scan its pages, decode the QRs -----


@pytest.mark.django_db
def test_qr_roundtrip_through_generated_pdf():
    """Generate a real PDF with QRs, then decode them back from each page."""
    pdfium = pytest.importorskip("pypdfium2")
    zxingcpp = pytest.importorskip("zxingcpp")

    from gsl_notification.tests.factories import (
        LettreNotificationFactory,
        ModeleLettreNotificationFactory,
    )
    from gsl_notification.utils import generate_pdf_for_generated_document
    from gsl_programmation.tests.factories import ProgrammationProjetFactory

    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__ds_number=7654321,
    )
    modele = ModeleLettreNotificationFactory(
        dotation=pp.dotation,
        perimetre=pp.dotation_projet.projet.dossier_ds.perimetre,
    )
    document = LettreNotificationFactory(
        programmation_projet=pp,
        modele=modele,
        content="<p>" + ("Contenu de test. " * 200) + "</p>",
    )

    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        pdf_bytes = generate_pdf_for_generated_document(document)

    pdf = pdfium.PdfDocument(pdf_bytes)
    decoded_per_page = []
    for page in pdf:
        image = page.render(scale=200 / 72).to_pil()
        payloads = [
            parse_payload(r.text)
            for r in zxingcpp.read_barcodes(image)
            if parse_payload(r.text) is not None
        ]
        decoded_per_page.append(payloads)

    assert len(decoded_per_page) >= 1
    for page_idx, payloads in enumerate(decoded_per_page, start=1):
        assert payloads, f"No GSL QR decoded on page {page_idx}"
        assert payloads[0] == QrPayload(
            ds_number=7654321,
            dotation=pp.dotation,
            document_type=document.document_type,
            page=page_idx,
        )


@pytest.mark.django_db
def test_decode_per_page_returns_bbox_in_bottom_left(tmp_path):
    """The detected bbox is small and sits in the bottom-left of the rendered image."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    from gsl_notification.tests.factories import (
        LettreNotificationFactory,
        ModeleLettreNotificationFactory,
    )
    from gsl_notification.utils import generate_pdf_for_generated_document
    from gsl_programmation.tests.factories import ProgrammationProjetFactory

    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__ds_number=1234567,
    )
    modele = ModeleLettreNotificationFactory(
        dotation=pp.dotation,
        perimetre=pp.dotation_projet.projet.dossier_ds.perimetre,
    )
    document = LettreNotificationFactory(
        programmation_projet=pp,
        modele=modele,
        content="<p>" + ("Contenu de test. " * 200) + "</p>",
    )

    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        pdf_bytes = generate_pdf_for_generated_document(document)

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    hits = decode_per_page(pdf_path)
    assert hits, "no pages decoded"

    for page_idx, hit in enumerate(hits, start=1):
        assert hit is not None, f"no QR on page {page_idx}"
        x, y, w, h = hit.bbox

        assert w > 0 and h > 0, f"empty bbox on page {page_idx}: {hit.bbox}"

        # Bottom-left quadrant of the rendered image.
        assert x + w < hit.image_width_px / 2, (
            f"bbox should be in left half, got x+w={x + w} vs width={hit.image_width_px}"
        )
        assert y > hit.image_height_px / 2, (
            f"bbox should be in bottom half, got y={y} vs height={hit.image_height_px}"
        )

        # Small relative to page (well under 10% of total area).
        image_area = hit.image_width_px * hit.image_height_px
        assert (w * h) < 0.1 * image_area, (
            f"bbox too large: area={w * h} vs image_area={image_area}"
        )


@pytest.mark.django_db
def test_no_qr_when_with_qr_code_is_false(tmp_path):
    """with_qr_code=False produces a PDF without any decodable GSL QR."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    from gsl_notification.tests.factories import (
        LettreNotificationFactory,
        ModeleLettreNotificationFactory,
    )
    from gsl_notification.utils import generate_pdf_for_generated_document
    from gsl_programmation.tests.factories import ProgrammationProjetFactory

    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__ds_number=2222222,
    )
    modele = ModeleLettreNotificationFactory(
        dotation=pp.dotation,
        perimetre=pp.dotation_projet.projet.dossier_ds.perimetre,
    )
    document = LettreNotificationFactory(
        programmation_projet=pp,
        modele=modele,
        content="<p>" + ("Contenu de test. " * 200) + "</p>",
    )

    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        pdf_bytes = generate_pdf_for_generated_document(document, with_qr_code=False)

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    hits = decode_per_page(pdf_path)
    assert hits, "no pages decoded"
    assert all(hit is None for hit in hits), (
        "no GSL QR should be present when with_qr_code=False"
    )

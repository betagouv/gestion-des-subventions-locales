import io
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from pikepdf import Page, Pdf

from gsl_core.tests.factories import CollegueFactory
from gsl_notification.models import LettreEtArreteSignes
from gsl_notification.qr import QrHit, QrPayload, parse_payload
from gsl_notification.tests.factories import (
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ARRETE, LETTRE


@pytest.fixture(autouse=True)
def _mock_logo():
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        yield


def _build_pdf_for_pp(ds_number, dotation=None, content_blocks=200):
    """Create a PP (with given ds_number) and return (pp, pdf bytes generated for it)."""
    from gsl_notification.utils import generate_pdf_for_generated_document

    kwargs = {"dotation_projet__projet__dossier_ds__ds_number": ds_number}
    if dotation is not None:
        kwargs["dotation_projet__dotation"] = dotation
    pp = ProgrammationProjetFactory(**kwargs)
    modele = ModeleLettreNotificationFactory(
        dotation=pp.dotation,
        perimetre=pp.dotation_projet.projet.dossier_ds.perimetre,
    )
    document = LettreNotificationFactory(
        programmation_projet=pp,
        modele=modele,
        content="<p>" + ("Contenu de test. " * content_blocks) + "</p>",
    )
    return pp, document, generate_pdf_for_generated_document(document)


def _concatenate(pdf_bytes_list, tmp_path, name="scan.pdf", shuffle=None):
    """Concatenate provided PDF byte-strings into a single PDF on disk."""
    merged = Pdf.new()
    sources = []
    try:
        pages = []
        for raw in pdf_bytes_list:
            src = Pdf.open(io.BytesIO(raw))
            sources.append(src)
            for page in src.pages:
                pages.append(page)
        if shuffle is not None:
            pages = [pages[i] for i in shuffle]
        for page in pages:
            merged.pages.append(page)
        out_path = tmp_path / name
        merged.save(str(out_path))
        return out_path
    finally:
        for s in sources:
            s.close()


@pytest.mark.django_db
def test_happy_path_splits_two_groups(tmp_path):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    user = CollegueFactory(email="op@example.com")

    pp1, _, pdf1 = _build_pdf_for_pp(ds_number=1111111)
    pp2, _, pdf2 = _build_pdf_for_pp(ds_number=2222222)

    pages_pp1 = len(Pdf.open(io.BytesIO(pdf1)).pages)
    pages_pp2 = len(Pdf.open(io.BytesIO(pdf2)).pages)

    total = pages_pp1 + pages_pp2
    # Reverse-shuffle: put pp2 pages first, pp1 pages second.
    shuffle = list(range(pages_pp1, total)) + list(range(0, pages_pp1))
    scan = _concatenate([pdf1, pdf2], tmp_path, shuffle=shuffle)

    call_command("reattach_signed_doc", str(scan), "--user", user.email)

    pp1.refresh_from_db()
    pp2.refresh_from_db()
    doc1 = LettreEtArreteSignes.objects.get(programmation_projet=pp1)
    doc2 = LettreEtArreteSignes.objects.get(programmation_projet=pp2)
    assert f"programmation_projet_{pp1.id}/" in doc1.file.name
    assert f"programmation_projet_{pp2.id}/" in doc2.file.name

    # Each stored group should hold exactly the pages that belonged to its PP,
    # even though the scan was shuffled. We don't decode QRs here because the
    # command strips them before storage; the unit test on `_group_pages` covers
    # the internal ordering.
    with doc1.file.open("rb") as fh:
        assert len(Pdf.open(io.BytesIO(fh.read())).pages) == pages_pp1
    with doc2.file.open("rb") as fh:
        assert len(Pdf.open(io.BytesIO(fh.read())).pages) == pages_pp2


def _decode_pdf_bytes(raw: bytes) -> list[QrPayload | None]:
    import pypdfium2 as pdfium
    import zxingcpp

    pdf = pdfium.PdfDocument(raw)
    try:
        out = []
        for page in pdf:
            image = page.render(scale=200 / 72).to_pil()
            found = None
            for r in zxingcpp.read_barcodes(image):
                found = parse_payload(r.text)
                if found:
                    break
            out.append(found)
        return out
    finally:
        pdf.close()


def test_group_pages_orders_lettre_before_arrete_then_by_page():
    """Unit test: `_group_pages` + the command's sort key place lettre pages
    before arrete pages, and order pages within each by the QR `page` field."""
    from gsl_notification.reattach import (
        _DOCUMENT_TYPE_ORDER,
        _group_pages,
    )

    def hit(ds, dotation, document_type, page):
        return QrHit(
            payload=QrPayload(
                ds_number=ds,
                dotation=dotation,
                document_type=document_type,
                page=page,
            ),
            bbox=(0.0, 0.0, 10.0, 10.0),
            image_width_px=1000,
            image_height_px=1000,
        )

    from gsl_projet.constants import DOTATION_DETR

    per_page = [
        hit(42, DOTATION_DETR, ARRETE, 2),  # scan idx 0
        hit(42, DOTATION_DETR, LETTRE, 1),  # scan idx 1
        hit(42, DOTATION_DETR, ARRETE, 1),  # scan idx 2
        hit(42, DOTATION_DETR, LETTRE, 2),  # scan idx 3
    ]
    groups, unreadable = _group_pages(per_page)
    assert unreadable == []
    entries = groups[(42, DOTATION_DETR)]
    entries.sort(key=lambda e: (_DOCUMENT_TYPE_ORDER.get(e[1], 99), e[2]))

    # Expected order: all LETTRE pages first (page 1 then 2), then ARRETE.
    assert [(e[0], e[1], e[2]) for e in entries] == [
        (1, LETTRE, 1),
        (3, LETTRE, 2),
        (2, ARRETE, 1),
        (0, ARRETE, 2),
    ]


@pytest.mark.django_db
def test_event_stream_emits_per_page_decode_events(tmp_path):
    """`reattach_signed_doc` should emit DecodeStarted, then a
    PageDecoded/UnreadablePage per page, then GroupAttached/Failed
    per group — in that order."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    from gsl_notification.reattach import (
        DecodeStarted,
        GroupAttached,
        PageDecoded,
        UnreadablePage,
        reattach_signed_doc,
    )

    user = CollegueFactory(email="op@example.com")
    pp, _, pdf_bytes = _build_pdf_for_pp(ds_number=6666666, content_blocks=1000)
    valid_page_count = len(Pdf.open(io.BytesIO(pdf_bytes)).pages)
    assert valid_page_count >= 2, (
        f"test assumes a multi-page generated PDF, got {valid_page_count}"
    )

    # Append a blank (unreadable) page to the valid scan.
    merged = Pdf.new()
    src = Pdf.open(io.BytesIO(pdf_bytes))
    try:
        for page in src.pages:
            merged.pages.append(page)
        merged.add_blank_page(page_size=(595, 842))
        scan = tmp_path / "scan_with_blank.pdf"
        merged.save(str(scan))
    finally:
        src.close()

    total_pages = valid_page_count + 1
    events = list(reattach_signed_doc(scan, user, name_stem=scan.stem))

    assert events[0] == DecodeStarted(total_pages=total_pages)

    per_page_events = events[1 : 1 + total_pages]
    expected_per_page = [
        PageDecoded(scan_page=i) for i in range(1, valid_page_count + 1)
    ]
    expected_per_page.append(UnreadablePage(scan_page=total_pages))
    assert per_page_events == expected_per_page

    assert len(events) == 1 + total_pages + 1
    assert isinstance(events[-1], GroupAttached)


@pytest.mark.django_db
def test_unreadable_page_is_skipped(tmp_path):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    user = CollegueFactory(email="op@example.com")
    pp, _, pdf_bytes = _build_pdf_for_pp(ds_number=3333333)

    # Append a blank page to a scan that otherwise covers a single group.
    merged = Pdf.new()
    src = Pdf.open(io.BytesIO(pdf_bytes))
    try:
        for page in src.pages:
            merged.pages.append(page)
        merged.add_blank_page(page_size=(595, 842))
        scan = tmp_path / "scan_with_blank.pdf"
        merged.save(str(scan))
    finally:
        src.close()

    blank_page_idx = len(Pdf.open(str(scan)).pages)  # 1-based

    with pytest.raises(CommandError) as exc:
        call_command("reattach_signed_doc", str(scan), "--user", user.email)

    assert str(blank_page_idx) in str(exc.value) or "unreadable" in str(exc.value)
    # The valid group is still committed despite the blank page.
    assert LettreEtArreteSignes.objects.filter(programmation_projet=pp).exists()


@pytest.mark.django_db
def test_unknown_ds_number_is_skipped(tmp_path):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    user = CollegueFactory(email="op@example.com")
    pp, _, pdf_bytes = _build_pdf_for_pp(ds_number=4444444)
    dotation = pp.dotation
    ds_number = pp.dotation_projet.projet.dossier_ds.ds_number

    # Persist a copy of the PDF, then drop the PP so lookup fails.
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(pdf_bytes)

    pp.delete()

    with pytest.raises(CommandError) as exc:
        call_command("reattach_signed_doc", str(scan), "--user", user.email)

    msg = str(exc.value)
    assert str(ds_number) in msg
    assert dotation in msg
    assert LettreEtArreteSignes.objects.count() == 0


@pytest.mark.django_db
def test_replaces_existing_lettre_et_arrete_signes(tmp_path):
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    user = CollegueFactory(email="op@example.com")
    pp, _, pdf_bytes = _build_pdf_for_pp(ds_number=5555555)

    pre = LettreEtArreteSignesFactory(
        programmation_projet=pp,
        file=SimpleUploadedFile(
            "old.pdf", b"old-content", content_type="application/pdf"
        ),
    )
    pre_id = pre.id

    scan = tmp_path / "scan.pdf"
    scan.write_bytes(pdf_bytes)

    call_command("reattach_signed_doc", str(scan), "--user", user.email)

    docs = LettreEtArreteSignes.objects.filter(programmation_projet=pp)
    assert docs.count() == 1
    new_doc = docs.get()
    assert new_doc.id != pre_id
    assert f"programmation_projet_{pp.id}/" in new_doc.file.name
    with new_doc.file.open("rb") as fh:
        new_content = fh.read()
    assert new_content != b"old-content"


def _paint_grey_background(pdf_bytes: bytes, rgb: tuple[float, float, float]) -> bytes:
    """Return a copy of `pdf_bytes` with a solid colour painted behind every page.

    Used as a stand-in for real scan paper texture: a uniform off-white tint
    that the masking code should sample and reproduce inside the QR area.
    """
    pdf = Pdf.open(io.BytesIO(pdf_bytes))
    try:
        r, g, b = rgb
        for page in pdf.pages:
            mb = page.MediaBox
            x0, y0 = float(mb[0]), float(mb[1])
            w = float(mb[2]) - x0
            h = float(mb[3]) - y0
            background = (
                f"q {r:.3f} {g:.3f} {b:.3f} rg "
                f"{x0:.3f} {y0:.3f} {w:.3f} {h:.3f} re f Q\n"
            ).encode("ascii")
            Page(page).contents_add(background, prepend=True)
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    finally:
        pdf.close()


@pytest.mark.django_db
def test_qr_mask_blends_in_with_surrounding_texture(tmp_path):
    """Patch over the QR should sample the page background, not paint white."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    import pypdfium2 as pdfium
    from PIL import ImageStat

    from gsl_notification.qr import RENDER_SCALE, decode_per_page

    user = CollegueFactory(email="op@example.com")
    pp, _, pdf_bytes = _build_pdf_for_pp(ds_number=9999991)

    # Tint every page with a uniform off-white so the swatch picker has a
    # non-white target to reproduce inside the QR area.
    tinted = _paint_grey_background(pdf_bytes, (0.78, 0.80, 0.82))
    scan = tmp_path / "scan_tinted.pdf"
    scan.write_bytes(tinted)

    # Locate the QR (in pixel space at the same scale we render at) before it
    # is masked, so we know exactly where to look in the stored PDF.
    hits = decode_per_page(scan)
    hit = next(h for h in hits if h is not None)

    call_command("reattach_signed_doc", str(scan), "--user", user.email)

    doc = LettreEtArreteSignes.objects.get(programmation_projet=pp)
    with doc.file.open("rb") as fh:
        stored_bytes = fh.read()

    stored_pdf = pdfium.PdfDocument(stored_bytes)
    try:
        rendered = stored_pdf[0].render(scale=RENDER_SCALE).to_pil().convert("RGB")
    finally:
        stored_pdf.close()

    x, y, w, h = (int(round(v)) for v in hit.bbox)
    inset = max(2, min(w, h) // 6)
    qr_area = rendered.crop((x + inset, y + inset, x + w - inset, y + h - inset))
    total_pixels = qr_area.width * qr_area.height
    counts = qr_area.getcolors(maxcolors=total_pixels) or []
    white_pixels = sum(count for count, pixel in counts if pixel == (255, 255, 255))
    mean = ImageStat.Stat(qr_area).mean

    assert white_pixels < total_pixels // 2, (
        "QR area looks like a white redaction patch, not blended texture: "
        f"{white_pixels}/{total_pixels} pure-white pixels (mean={mean})"
    )
    assert max(mean) < 250, (
        f"QR area is ~white (mean={mean}); patch did not pick up the tint"
    )

    # Sanity: a point well outside the QR should still carry the original tint
    # (i.e. the patch did not paint over the rest of the page).
    far_x, far_y = max(0, x - 60), max(0, y - 60)
    surround = rendered.getpixel((far_x, far_y))
    assert max(surround) < 250, (
        f"Surrounding background was unexpectedly clobbered: {surround}"
    )


@pytest.mark.django_db
def test_qr_is_removed_from_stored_pdf(tmp_path):
    """The command must strip QRs before storing — end-users never see them."""
    pytest.importorskip("pypdfium2")
    pytest.importorskip("zxingcpp")

    user = CollegueFactory(email="op@example.com")
    pp, _, pdf_bytes = _build_pdf_for_pp(ds_number=8888888)

    # Sanity: the generated (pre-masking) PDF carries decodable QRs.
    pre_decoded = _decode_pdf_bytes(pdf_bytes)
    assert any(p is not None for p in pre_decoded), (
        "generated PDF should carry QRs before reattachment"
    )

    scan = tmp_path / "scan.pdf"
    scan.write_bytes(pdf_bytes)

    call_command("reattach_signed_doc", str(scan), "--user", user.email)

    doc = LettreEtArreteSignes.objects.get(programmation_projet=pp)
    with doc.file.open("rb") as fh:
        stored_decoded = _decode_pdf_bytes(fh.read())

    assert stored_decoded, "stored PDF should have at least one page"
    assert all(p is None for p in stored_decoded), (
        f"expected no GSL QR in stored PDF, found: {stored_decoded}"
    )

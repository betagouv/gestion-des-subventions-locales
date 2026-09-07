"""
Read a scanned signed PDF, decode the QR code on each page, and split the scan
into one signed document (lettre/arrêté, or lettre de refus) per matching
ProgrammationProjet.

Thin CLI wrapper around `gsl_notification.qr.reattach.reattach_signed_docs`,
which the web import flow calls too. Matching is global here, where the web
flow scopes it to the importer's perimetre.

Usage:
    python manage.py reattach_signed_doc path/to/scan.pdf --user me@example.com
"""

from collections import defaultdict
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from gsl_core.models import Collegue
from gsl_notification.qr.reattach import (
    DOCUMENT_TYPE_ORDER,
    DecodeStarted,
    DocumentAttached,
    MatchFailed,
    PageDecoded,
    reattach_signed_docs,
)
from gsl_programmation.models import ProgrammationProjet

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class Command(BaseCommand):
    help = (
        "Decode the per-page QR codes from a scanned signed PDF and reattach "
        "each document it contains to its ProgrammationProjet, as the matching "
        "signed-document type (lettre/arrêté or lettre de refus)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "pdf_path",
            type=str,
            help="Path to the scanned signed PDF.",
        )
        parser.add_argument(
            "--user",
            required=True,
            help="Email of the Collegue to record as created_by.",
        )

    def handle(self, *args, **options):
        pdf_path = Path(options["pdf_path"]).expanduser().resolve()
        if not pdf_path.is_file():
            raise CommandError(f"File not found: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise CommandError(f"Not a PDF: {pdf_path}")

        try:
            user = Collegue.objects.get(email=options["user"])
        except Collegue.DoesNotExist:
            raise CommandError(f"No Collegue with email {options['user']!r}")

        pdfs = [ContentFile(pdf_path.read_bytes(), name=pdf_path.name)]
        attached, unreadable, unmatched = self._consume_events(
            reattach_signed_docs(pdfs, user, ProgrammationProjet.objects.all())
        )

        self._print_summary(attached, unreadable, unmatched)

        if unreadable or unmatched:
            raise CommandError(_format_issue_report(attached, unreadable, unmatched))

    def _consume_events(self, events):
        attached: list[str] = []
        unmatched: list[str] = []
        unreadable: list[int] = []
        progress = None
        try:
            for event in events:
                if isinstance(event, DecodeStarted):
                    if tqdm is not None:
                        progress = tqdm(
                            total=event.total_pages, unit="page", desc="Decoding"
                        )
                elif isinstance(event, PageDecoded):
                    if progress is not None:
                        progress.update(1)
                    if not event.qr_found:
                        unreadable.append(event.scan_page)
                elif isinstance(event, DocumentAttached):
                    attached.append(_format_attached(event.document))
                elif isinstance(event, MatchFailed):
                    unmatched.append(_format_failed(event))
        finally:
            if progress is not None:
                progress.close()
        return attached, unreadable, unmatched

    def _print_summary(self, attached, unreadable, unmatched):
        self.stdout.write(f"Attached {len(attached)} document(s):")
        for line in attached:
            self.stdout.write(f"  {line}")
        self.stdout.write(f"Skipped {len(unreadable)} unreadable page(s).")
        if unreadable:
            self.stdout.write(f"  pages: {unreadable}")
        self.stdout.write(f"Matched no ProgrammationProjet: {len(unmatched)}.")
        for line in unmatched:
            self.stdout.write(f"  {line}")


def _format_page_range(pages):
    if not pages:
        return ""
    if len(pages) == 1:
        return str(pages[0])
    if pages == list(range(pages[0], pages[-1] + 1)):
        return f"{pages[0]}–{pages[-1]}"
    return ", ".join(str(p) for p in pages)


def _scan_pages_by_doc_type(document) -> dict[str, list[int]]:
    by_doc_type = defaultdict(list)
    for page in document.pages:
        by_doc_type[page.doc_type].append(page.scan_index + 1)
    return {doc_type: sorted(pages) for doc_type, pages in by_doc_type.items()}


def _format_attached(document) -> str:
    pages_by_doc_type = _scan_pages_by_doc_type(document)
    breakdown = ", ".join(
        f"{doc_type}: pages {_format_page_range(pages_by_doc_type[doc_type])}"
        for doc_type in sorted(
            pages_by_doc_type, key=lambda t: DOCUMENT_TYPE_ORDER.get(t, 99)
        )
    )
    declared = document.declared
    return (
        f"ds={declared.ds_number} dotation={declared.dotation} "
        f"[{declared.target_model.document_type}] → "
        f"ProgrammationProjet #{document.programmation_projet_id} ({breakdown})"
    )


def _format_failed(event) -> str:
    declared = event.declared
    return f"ds={declared.ds_number} dotation={declared.dotation}: {event.error}"


def _format_issue_report(
    attached: list[str], unreadable: list[int], unmatched: list[str]
) -> str:
    details = []
    if unreadable:
        details.append(f"unreadable pages: {unreadable}")
    if unmatched:
        details.append("unmatched documents: " + "; ".join(unmatched))
    return (
        f"Completed with issues: {len(unreadable)} unreadable page(s), "
        f"{len(unmatched)} unmatched document(s). "
        f"{len(attached)} document(s) attached successfully. " + " | ".join(details)
    )

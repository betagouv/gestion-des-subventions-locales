"""
POC command: read a scanned signed PDF, decode the QR code on each page, and
split the scan into one LettreEtArreteSignes per matching ProgrammationProjet.

Thin CLI wrapper around `gsl_notification.reattach.reattach_signed_doc`;
the underlying business logic is shared with the future upload view.

Usage:
    python manage.py reattach_signed_doc path/to/scan.pdf --user me@example.com
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from gsl_core.models import Collegue
from gsl_notification.reattach import (
    _DOCUMENT_TYPE_ORDER,
    DecodeStarted,
    GroupAttached,
    GroupFailed,
    PageDecoded,
    UnreadablePage,
    _format_page_range,
    reattach_signed_doc,
)

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class Command(BaseCommand):
    help = (
        "POC: decode the per-page QR codes from a scanned signed PDF and "
        "reattach each detected group to its ProgrammationProjet as a "
        "LettreEtArreteSignes."
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

        attached, unreadable, failed_groups = self._consume_events(
            reattach_signed_doc(pdf_path, user, name_stem=pdf_path.stem)
        )

        self._print_summary(attached, unreadable, failed_groups)

        if unreadable or failed_groups:
            raise CommandError(
                _format_issue_report(attached, unreadable, failed_groups)
            )

    def _consume_events(self, events):
        attached: list[str] = []
        failed_groups: list[str] = []
        unreadable: list[int] = []
        progress = None
        try:
            for event in events:
                if isinstance(event, DecodeStarted):
                    if tqdm is not None:
                        progress = tqdm(
                            total=event.total_pages, unit="page", desc="Decoding"
                        )
                elif isinstance(event, (PageDecoded, UnreadablePage)):
                    if progress is not None:
                        progress.update(1)
                    if isinstance(event, UnreadablePage):
                        unreadable.append(event.scan_page)
                elif isinstance(event, GroupAttached):
                    attached.append(_format_attached(event.report))
                elif isinstance(event, GroupFailed):
                    failed_groups.append(_format_failed(event.report))
        finally:
            if progress is not None:
                progress.close()
        return attached, unreadable, failed_groups

    def _print_summary(self, attached, unreadable, failed_groups):
        self.stdout.write(f"Attached {len(attached)} group(s):")
        for line in attached:
            self.stdout.write(f"  {line}")
        self.stdout.write(f"Skipped {len(unreadable)} unreadable page(s).")
        if unreadable:
            self.stdout.write(f"  pages: {unreadable}")
        self.stdout.write(f"Failed {len(failed_groups)} group(s).")
        for line in failed_groups:
            self.stdout.write(f"  {line}")


def _format_attached(report) -> str:
    breakdown = ", ".join(
        f"{doc_type}: pages {_format_page_range(report.pages_by_doc_type[doc_type])}"
        for doc_type in sorted(
            report.pages_by_doc_type, key=lambda t: _DOCUMENT_TYPE_ORDER.get(t, 99)
        )
    )
    return (
        f"ds={report.ds_number} dotation={report.dotation} → "
        f"ProgrammationProjet #{report.programmation_projet_id} ({breakdown})"
    )


def _format_failed(report) -> str:
    return f"ds={report.ds_number} dotation={report.dotation}: {report.error}"


def _format_issue_report(
    attached: list[str], unreadable: list[int], failed_groups: list[str]
) -> str:
    details = []
    if unreadable:
        details.append(f"unreadable pages: {unreadable}")
    if failed_groups:
        details.append("unrouted groups: " + "; ".join(failed_groups))
    return (
        f"Completed with issues: {len(unreadable)} unreadable page(s), "
        f"{len(failed_groups)} unrouted group(s). "
        f"{len(attached)} group(s) attached successfully. " + " | ".join(details)
    )

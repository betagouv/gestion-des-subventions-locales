import io
from decimal import Decimal, InvalidOperation

import img2pdf
from django.core.files.uploadedfile import SimpleUploadedFile
from pikepdf import Pdf

from gsl.core.s3 import get_s3_object
from gsl.notification.models import UploadedDocument


def order_couples_tuple_by_first_value(
    choices: tuple[tuple[str, str], ...], ordered_first_values: tuple[str, ...]
):
    order_dict = {status: index for index, status in enumerate(ordered_first_values)}
    return sorted(
        choices,
        key=lambda x: order_dict[x[0]] if x[0] in order_dict else 1,
    )


def transform_choices_to_map(choices: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return {key: value for key, value in choices}


def compute_taux(
    numerator: float | Decimal,
    denominator: float | Decimal,
    decimals: int | None = None,
) -> Decimal:
    try:
        if decimals is None:
            taux = Decimal(numerator) / Decimal(denominator) * 100
        else:
            taux = round((Decimal(numerator) / Decimal(denominator)) * 100, decimals)
        return max(taux, Decimal(0))
    except TypeError:
        return Decimal(0)
    except ZeroDivisionError:
        return Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def floatize(value: float | Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def get_comment_cards(projet):
    """Retourne la liste des cartes commentaires d'arbitrage pour le template."""

    from ..forms import ProjetCommentForm

    return [
        {
            "num": "1",
            "value": projet.comment_1,
            "form": ProjetCommentForm(initial={"comment_number": "1"}, instance=projet),
        },
        {
            "num": "2",
            "value": projet.comment_2,
            "form": ProjetCommentForm(initial={"comment_number": "2"}, instance=projet),
        },
        {
            "num": "3",
            "value": projet.comment_3,
            "form": ProjetCommentForm(initial={"comment_number": "3"}, instance=projet),
        },
    ]


def merge_documents_into_pdf(
    documents: list[UploadedDocument],
    filename: str = "documents.pdf",
) -> SimpleUploadedFile:
    documents_file_bytes = [_get_uploaded_document_pdf(doc) for doc in documents]
    return SimpleUploadedFile(
        name=filename,
        content=merge_pdf_bytes(documents_file_bytes),
        content_type="application/pdf",
    )


def _get_uploaded_document_pdf(document: UploadedDocument) -> io.BytesIO:
    s3_object = get_s3_object(document.file.name)
    content = s3_object["Body"].read()

    output = io.BytesIO()
    output.write(
        content
        if s3_object["ContentType"] == "application/pdf"
        else img2pdf.convert(
            content,
            layout_fun=img2pdf.get_layout_fun(
                (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
            ),  # A4
        )
    )
    return output


def merge_pdf_bytes(files: list[io.BytesIO]) -> bytes:
    pdf = Pdf.new()

    for file in files:
        src = Pdf.open(file)
        pdf.pages.extend(src.pages)

    output = io.BytesIO()
    pdf.save(output)
    return output.getvalue()

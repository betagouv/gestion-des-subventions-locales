import base64
import io
import os
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

import boto3
import img2pdf
import requests
from bs4 import BeautifulSoup, NavigableString
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe
from django_weasyprint.utils import django_url_fetcher
from num2words import num2words
from pikepdf import Pdf
from weasyprint import HTML

from gsl_core.exceptions import Http404
from gsl_core.models import Perimetre
from gsl_core.templatetags.gsl_filters import euro, percent
from gsl_notification.models import (
    Annexe,
    Arrete,
    LettreEtArreteSignes,
    LettreNotification,
    ModeleArrete,
    ModeleLettreNotification,
)
from gsl_notification.qr import build_payload, generate_qr_png_data_uri
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    ANNEXE,
    ARRETE,
    DOTATION_DETR,
    LETTRE,
    LETTRE_ET_ARRETE_SIGNES,
    POSSIBLE_DOTATIONS,
    POSSIBLES_DOCUMENTS,
    POSSIBLES_DOCUMENTS_TELEVERSABLES,
)


def get_nested_attribute(obj, attribute_path):
    """
    Récupère un attribut imbriqué en utilisant la notation en points.
    Par exemple: get_nested_attribute(programmation_projet, "dossier.date_achevement")
    Retourne None si un intermédiaire est None ou si une relation inverse n'existe pas.
    """
    attributes = attribute_path.split(".")
    current_obj = obj
    for attr in attributes:
        if current_obj is None:
            return None
        try:
            current_obj = getattr(current_obj, attr)
        except ObjectDoesNotExist:
            return None
    return current_obj


class MentionType(Enum):
    STRING = "string"
    EURO = "euro"
    EURO_LETTRES = "euro_lettres"
    PERCENT = "percent"
    DATE = "date"
    DATE_NOW = "date_now"
    TEXT_ONLY = "text_only"


@dataclass(frozen=True)
class Mention:
    key: str
    label: str
    attribute: str
    type: MentionType = MentionType.STRING

    def get_value(self, programmation_projet: ProgrammationProjet) -> str:
        if self.type == MentionType.DATE_NOW:
            return timezone.now().strftime("%d/%m/%Y")
        value = get_nested_attribute(programmation_projet, self.attribute)
        match self.type:
            case MentionType.EURO:
                return euro(value, 2) if value is not None else "N/A"
            case MentionType.EURO_LETTRES:
                return (
                    num2words(value, lang="fr", to="currency", currency="EUR")
                    if value is not None
                    else "N/A"
                )
            case MentionType.PERCENT:
                return percent(value, 2) if value is not None else "N/A"
            case MentionType.DATE:
                return value.strftime("%d/%m/%Y") if value else "N/A"
            case MentionType.TEXT_ONLY:
                return BeautifulSoup(value, "html.parser").get_text() if value else ""
            case _:
                return str(value) if value is not None else ""


MENTIONS = [
    Mention("numero-dossier", "Numéro DN du dossier", "dossier.ds_number"),
    Mention(
        "date-depot",
        "Date de dépôt du dossier",
        "dossier.ds_date_depot",
        MentionType.DATE,
    ),
    Mention("nom-beneficiaire", "Nom du bénéficiaire", "dossier.ds_demandeur"),
    Mention(
        "siret-beneficiaire", "SIRET du bénéficiaire", "dossier.ds_demandeur.siret"
    ),
    Mention("projet-intitule", "Intitulé du projet", "dossier.projet_intitule"),
    Mention(
        "nom-departement", "Nom du département", "projet.perimetre.departement.name"
    ),
    Mention(
        "cout-total",
        "Coût total de l'opération",
        "dossier.finance_cout_total",
        MentionType.EURO,
    ),
    Mention("assiette", "Assiette", "dotation_projet.assiette", MentionType.EURO),
    Mention(
        "montant-subvention",
        "Montant accordé",
        "montant",
        MentionType.EURO,
    ),
    Mention(
        "montant-subvention-lettres",
        "Montant accordé (toutes lettres)",
        "montant",
        MentionType.EURO_LETTRES,
    ),
    Mention("taux-subvention", "Taux de subvention", "taux", MentionType.PERCENT),
    Mention(
        "date-commencement",
        "Date de commencement",
        "dossier.date_debut",
        MentionType.DATE,
    ),
    Mention(
        "date-achevement",
        "Date d'achèvement",
        "dossier.date_achevement",
        MentionType.DATE,
    ),
    Mention(
        "porteur-fonction",
        "Fonction du porteur de projet",
        "dossier.porteur_de_projet_fonction",
    ),
    Mention(
        "porteur-civilite",
        "Civilité du porteur de projet",
        "dossier.porteur_de_projet_civilite",
    ),
    Mention(
        "porteur-prenom",
        "Prénom du porteur de projet",
        "dossier.porteur_de_projet_prenom",
    ),
    Mention("porteur-nom", "Nom du porteur de projet", "dossier.porteur_de_projet_nom"),
    Mention(
        "adresse-demandeur",
        "Adresse du demandeur",
        "dossier.ds_demandeur.address.two_lines",
    ),
    Mention(
        "date-arrete",
        "Date d'édition de l'arrêté",
        "",
        MentionType.DATE_NOW,
    ),
    Mention(
        "commentaire-1",
        "Commentaire 1",
        "projet.comment_1",
        MentionType.TEXT_ONLY,
    ),
    Mention(
        "commentaire-2",
        "Commentaire 2",
        "projet.comment_2",
        MentionType.TEXT_ONLY,
    ),
    Mention(
        "commentaire-3",
        "Commentaire 3",
        "projet.comment_3",
        MentionType.TEXT_ONLY,
    ),
]


MENTION_KEY_TO_MENTION: dict[str, Mention] = {m.key: m for m in MENTIONS}


def replace_mentions_in_html(
    htmlContent: str, programmation_projet: ProgrammationProjet
):
    soup = BeautifulSoup(htmlContent, "html.parser")

    for span in soup.find_all("span", class_="mention"):
        key = span.get("data-id")
        if key not in MENTION_KEY_TO_MENTION:
            raise ValueError(f"Mention {key!r} inconnue.")
        value = MENTION_KEY_TO_MENTION[key].get_value(programmation_projet)
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if "\n" in normalized:
            lines = normalized.split("\n")
            fragment = BeautifulSoup("", "html.parser")
            for i, line in enumerate(lines):
                fragment.append(NavigableString(line))
                if i < len(lines) - 1:
                    fragment.append(soup.new_tag("br"))
            span.replace_with(fragment)
        else:
            span.replace_with(value)

    return str(soup)


def update_file_name_to_put_it_in_a_programmation_projet_folder(
    file, programmation_projet_id: int, is_annexe=False
):
    original_name = file.name
    base_name, extension = os.path.splitext(original_name)

    if is_annexe:
        pp = ProgrammationProjet.objects.get(pk=programmation_projet_id)
        existing_names = [annexe.name for annexe in pp.annexes.all()]

        # Check for duplicates and add version number if needed
        counter = 1
        new_name = original_name
        while new_name in existing_names:
            counter += 1
            new_name = f"{base_name}_{counter}{extension}"

        file.name = new_name

    new_file_name = f"programmation_projet_{programmation_projet_id}/{file.name}"
    file.name = new_file_name


def get_modele_perimetres(
    dotation: POSSIBLE_DOTATIONS, perimetre: Perimetre
) -> list[Perimetre]:
    """
    | user périmètre | DETR                     | DSIL                       |
    | -------------- | ------------------------ | -------------------------- |
    | Arrondissement | Mon arrondissement + dpt | Mon arrond. + dpt + région |
    | Département    | Mon dpt                  | Mon arrond. + région       |
    | Région         | /                        | Ma région                  |
    """
    try:
        if dotation == DOTATION_DETR:
            if perimetre.type == Perimetre.TYPE_ARRONDISSEMENT:
                return [
                    perimetre,
                    Perimetre.objects.get(
                        arrondissement=None, departement=perimetre.departement
                    ),
                ]
            elif perimetre.type == Perimetre.TYPE_DEPARTEMENT:
                return [perimetre]
            else:
                raise ValueError(
                    "Les modèles de la dotation DETR ne sont pas accessibles pour les utilisateurs dont le périmètre n'est pas de type arrondissement ou départemental."
                )

        # DSIL
        if perimetre.type == Perimetre.TYPE_ARRONDISSEMENT:
            return [
                perimetre,
                Perimetre.objects.get(
                    arrondissement=None, departement=perimetre.departement
                ),
                Perimetre.objects.get(
                    arrondissement=None, departement=None, region=perimetre.region
                ),
            ]
        elif perimetre.type == Perimetre.TYPE_DEPARTEMENT:
            return [
                perimetre,
                Perimetre.objects.get(
                    arrondissement=None, departement=None, region=perimetre.region
                ),
            ]

        return [perimetre]

    except Perimetre.DoesNotExist:
        return [perimetre]


def duplicate_field_file(field_file: FieldFile):
    """
    Retourne (nouveau_nom, file_obj)
    Copie le contenu du fichier stocké derrière `field_file`.
    """
    if not field_file:
        return None, None

    base_name = os.path.basename(field_file.name)
    root, ext = os.path.splitext(base_name)

    # remove token (underscore + 11 random characters at the end):
    # a new one will be added (see tokenized_file_in_timestamped_folder)
    root_without_token = root[:-12]
    root = root_without_token if root_without_token else root

    new_name = f"{root}{ext}"

    # Copie efficace sans tout lire en mémoire (streaming)
    storage = field_file.storage
    with storage.open(field_file.name, "rb") as src:
        # File() wrappe le descripteur ouvert pour Django
        return new_name, File(src, name=new_name)


def get_s3_object(file_name):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    try:
        return s3.get_object(Bucket=bucket, Key=file_name)
    except s3.exceptions.NoSuchKey:
        raise Http404(user_message="Fichier non trouvé")


def get_modele_class(modele_type):
    if modele_type not in [ARRETE, LETTRE]:
        raise ValueError("Type inconnu")
    if modele_type == LETTRE:
        return ModeleLettreNotification
    return ModeleArrete


def get_generated_document_class(document_type):
    if document_type not in [ARRETE, LETTRE]:
        raise ValueError("Type inconnu")
    if document_type == LETTRE:
        return LettreNotification
    return Arrete


def get_form_class(document_type):
    from gsl_notification.forms import ArreteForm, LettreNotificationForm

    if document_type not in [ARRETE, LETTRE]:
        raise ValueError("Type inconnu")
    if document_type == LETTRE:
        return LettreNotificationForm
    return ArreteForm


def get_doc_title(document_type: POSSIBLES_DOCUMENTS):
    if document_type not in [ARRETE, LETTRE]:
        raise ValueError(f"Document type {document_type} inconnu")
    if document_type == LETTRE:
        return "Lettre de notification"
    return "Arrêté d'attribution"


def get_programmation_projet_attribute(document_type: POSSIBLES_DOCUMENTS):
    if document_type not in [ARRETE, LETTRE]:
        raise ValueError(f"Document type {document_type} inconnu")
    if document_type == LETTRE:
        return "lettre_notification"
    return "arrete"


def get_uploaded_document_class(document_type: POSSIBLES_DOCUMENTS_TELEVERSABLES):
    if document_type not in [LETTRE_ET_ARRETE_SIGNES, ANNEXE]:
        raise ValueError(f"Document type {document_type} inconnu")
    if document_type == ANNEXE:
        return Annexe
    return LettreEtArreteSignes


def get_uploaded_form_class(document_type: POSSIBLES_DOCUMENTS_TELEVERSABLES):
    from gsl_notification.forms import AnnexeForm, ArreteEtLettreSigneForm

    if document_type not in [LETTRE_ET_ARRETE_SIGNES, ANNEXE]:
        raise ValueError(f"Document type {document_type} inconnu")
    if document_type == ANNEXE:
        return AnnexeForm
    return ArreteEtLettreSigneForm


@lru_cache(maxsize=32)
def get_logo_base64(url):
    response = requests.get(url)
    response.raise_for_status()
    return "data:image/png;base64," + base64.b64encode(response.content).decode("utf-8")


def _get_uploaded_document_pdf(document: Annexe | LettreEtArreteSignes) -> io.BytesIO:
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


def fix_empty_paragraphs_for_weasyprint(html: str) -> str:
    """
    WeasyPrint (comme les navigateurs) collapse les <p> qui ne contiennent que du
    whitespace ou des <br> (ils finissent avec une hauteur nulle).
    On remplace leur contenu par un espace insécable pour préserver les sauts de
    ligne issus d'un éditeur riche.
    """
    soup = BeautifulSoup(html, "html.parser")
    for p in soup.find_all("p"):
        # get_text(strip=True) retire les espaces, tabs, \n — si vide, le <p> est
        # visuellement vide (contient uniquement du whitespace et/ou des <br>)
        if not p.get_text(strip=True):
            p.clear()
            p.append("\u00a0")
    return str(soup)


# Approximate pixel width of the TipTap editor content area, used as the
# reference base when converting absolute pixel widths to CSS percentages for
# PDF rendering. Tables narrower than the full editor width are preserved at
# their proportional size (e.g. 450px → 50% on a 900px reference).
_TIPTAP_EDITOR_REFERENCE_WIDTH_PX = 900


def fix_table_widths_for_weasyprint(html: str) -> str:
    """
    TipTap (resizable: true) stores column widths in pixels in <colgroup>.
    WeasyPrint honours inline styles over the pdf.css `width: 100%` rule,
    causing tables to overflow the page.

    - Table has `width: Xpx`: convert to a percentage of
      _TIPTAP_EDITOR_REFERENCE_WIDTH_PX so narrow tables stay narrow in PDF.
    - Table has only `min-width: Xpx`: remove the inline style (CSS handles
      it); full-width tables with resized columns fall into this case.

    Col pixel widths are converted to proportional percentages in both cases.
    Columns without an explicit width share the remaining percentage equally.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        result = _table_total_and_style(table)
        if result is None:
            table.attrs.pop("style", None)
            for col in table.find_all("col"):
                col.attrs.pop("style", None)
                col.attrs.pop("width", None)
            continue
        total, new_style = result
        if new_style:
            table.attrs["style"] = new_style
        else:
            table.attrs.pop("style", None)
        cols = table.find_all("col")
        if cols:
            _apply_col_pct_widths(cols, total)
    return str(soup)


def _table_total_and_style(table) -> tuple[float, str | None] | None:
    """
    Parse the table's inline style to determine the column width reference.
    Returns (total_px, new_style) where new_style is the replacement inline
    style for the table element (None = remove it, let CSS width: 100% apply).
    Returns None if the table carries no parseable pixel width.
    """
    style = table.get("style", "")
    width_match = re.search(r"(?<!-)width\s*:\s*([\d.]+)px", style)
    if width_match:
        table_px = float(width_match.group(1))
        pct = table_px / _TIPTAP_EDITOR_REFERENCE_WIDTH_PX * 100
        return table_px, f"width: {pct:.2f}%"
    min_width_match = re.search(r"min-width\s*:\s*([\d.]+)px", style)
    if min_width_match:
        return float(min_width_match.group(1)), None
    return None


def _col_width_px(col) -> float | None:
    """Return the explicit pixel width of a <col>, or None if unset."""
    w_match = re.search(r"(?<!-)width\s*:\s*([\d.]+)px", col.get("style", ""))
    if w_match:
        return float(w_match.group(1))
    html_w = col.get("width")
    if html_w:
        try:
            return float(html_w)
        except ValueError:
            pass
    return None


def _apply_col_pct_widths(cols, total: float) -> None:
    """Convert pixel col widths to percentages of `total`. No-op if all are None."""
    col_widths = [_col_width_px(col) for col in cols]
    if all(w is None for w in col_widths):
        return
    known_sum = sum(w for w in col_widths if w is not None)
    n_unknown = col_widths.count(None)
    remaining_pct = 100 - known_sum / total * 100
    unknown_pct = remaining_pct / n_unknown if n_unknown else 0
    for col, w in zip(cols, col_widths):
        col.attrs.pop("style", None)
        col.attrs.pop("width", None)
        pct = w / total * 100 if w is not None else unknown_pct
        col.attrs["style"] = f"width: {pct:.2f}%"


def generate_pdf_for_generated_document(
    document: Arrete | LettreNotification, *, with_qr_code: bool = True
) -> bytes:
    """
    Generate PDF bytes for a GeneratedDocument (Arrete or LettreNotification).

    When ``with_qr_code`` is True (default), a per-page QR code is rendered at
    the bottom-left of every page so a scanned, signed copy can be reattached
    to the right ProgrammationProjet. Because each page needs a *different* QR
    (the payload includes the page number), this is a two-pass render: first
    pass counts pages, second pass emits one ``@page :nth(K)`` rule per page
    with the matching QR image.

    When ``with_qr_code`` is False, a single, faster pass is rendered without
    any QR code.
    """
    content = fix_empty_paragraphs_for_weasyprint(document.content)
    content = fix_table_widths_for_weasyprint(content)
    base_context = {
        "doc_title": get_doc_title(document.document_type),
        "logo": get_logo_base64(document.modele.logo.url),
        "alt_logo": document.modele.logo_alt_text,
        "top_right_text": document.modele.top_right_text.strip(),
        "content": mark_safe(content),
    }

    if not with_qr_code:
        html = render_to_string(
            "gsl_notification/pdf/document.html",
            {**base_context, "qr_css_rules": ""},
        )
        return HTML(
            string=html,
            url_fetcher=django_url_fetcher,
            base_url=settings.STATIC_ROOT,
        ).write_pdf()

    # Pass 1: render without QR to learn how many pages the document has.
    first_pass_html = render_to_string(
        "gsl_notification/pdf/document.html",
        {**base_context, "qr_css_rules": ""},
    )
    first_pass_pdf = HTML(
        string=first_pass_html,
        url_fetcher=django_url_fetcher,
        base_url=settings.STATIC_ROOT,
    ).write_pdf()

    qr_css_rules = _build_qr_css_rules(document, _count_pdf_pages(first_pass_pdf))

    # Pass 2: render again with one @page :nth(K) rule per page.
    final_html = render_to_string(
        "gsl_notification/pdf/document.html",
        {**base_context, "qr_css_rules": mark_safe(qr_css_rules)},
    )
    return HTML(
        string=final_html,
        url_fetcher=django_url_fetcher,
        base_url=settings.STATIC_ROOT,
    ).write_pdf()


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    with Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def _build_qr_css_rules(document: Arrete | LettreNotification, page_count: int) -> str:
    """Return CSS with one ``@page :nth(K)`` rule per page, each carrying its QR."""
    ds_number = document.programmation_projet.dossier.ds_number
    dotation = document.programmation_projet.dotation
    document_type = document.document_type

    rules = []
    for page in range(1, page_count + 1):
        payload = build_payload(ds_number, dotation, document_type, page)
        data_uri = generate_qr_png_data_uri(payload)
        rules.append(
            f"@page :nth({page}) {{ @bottom-left {{ content: url('{data_uri}'); }} }}"
        )
    return "\n".join(rules)


def merge_documents_into_pdf(
    documents: list[LettreEtArreteSignes | Annexe],
) -> SimpleUploadedFile:
    documents_file_bytes = [_get_uploaded_document_pdf(doc) for doc in documents]

    pdf = Pdf.new()

    for file in documents_file_bytes:
        src = Pdf.open(file)
        pdf.pages.extend(src.pages)

    bytes = io.BytesIO()
    pdf.save(bytes)
    bytes.seek(0)
    return SimpleUploadedFile(
        name="documents.pdf", content=bytes.read(), content_type="application/pdf"
    )

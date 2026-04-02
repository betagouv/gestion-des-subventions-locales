import base64
import io
import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

import boto3
import img2pdf
import requests
from bs4 import BeautifulSoup
from django.conf import settings
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
    ArreteEtLettreSignes,
    LettreNotification,
    ModeleArrete,
    ModeleLettreNotification,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    ANNEXE,
    ARRETE,
    ARRETE_ET_LETTRE_SIGNES,
    DOTATION_DETR,
    LETTRE,
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
        current_obj = getattr(current_obj, attr)
    return current_obj


class MentionType(Enum):
    STRING = "string"
    EURO = "euro"
    EURO_LETTRES = "euro_lettres"
    PERCENT = "percent"
    DATE = "date"
    DATE_ARRETE = "date_arrete"
    TEXT_ONLY = "text_only"


@dataclass(frozen=True)
class Mention:
    key: str
    label: str
    attribute: str
    type: MentionType = MentionType.STRING

    def get_value(self, programmation_projet: ProgrammationProjet) -> str:
        if self.type == MentionType.DATE_ARRETE:
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
        "dossier.ds_demandeur.address",
    ),
    Mention(
        "date-arrete",
        "Date d'édition de l'arrêté",
        "arrete.created_at",
        MentionType.DATE_ARRETE,
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
        span.replace_with(MENTION_KEY_TO_MENTION[key].get_value(programmation_projet))

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
    if document_type not in [ARRETE_ET_LETTRE_SIGNES, ANNEXE]:
        raise ValueError(f"Document type {document_type} inconnu")
    if document_type == ANNEXE:
        return Annexe
    return ArreteEtLettreSignes


def get_uploaded_form_class(document_type: POSSIBLES_DOCUMENTS_TELEVERSABLES):
    from gsl_notification.forms import AnnexeForm, ArreteEtLettreSigneForm

    if document_type not in [ARRETE_ET_LETTRE_SIGNES, ANNEXE]:
        raise ValueError(f"Document type {document_type} inconnu")
    if document_type == ANNEXE:
        return AnnexeForm
    return ArreteEtLettreSigneForm


@lru_cache(maxsize=32)
def get_logo_base64(url):
    response = requests.get(url)
    response.raise_for_status()
    return "data:image/png;base64," + base64.b64encode(response.content).decode("utf-8")


def _get_uploaded_document_pdf(document: Annexe | ArreteEtLettreSignes) -> io.BytesIO:
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


def generate_pdf_for_generated_document(document: Arrete | LettreNotification) -> bytes:
    """
    Generate PDF bytes for a GeneratedDocument (Arrete or LettreNotification).

    This function generates the PDF content for a document and returns it as bytes.
    It can be used to calculate the document size without actually serving it.
    """
    context = {
        "doc_title": get_doc_title(document.document_type),
        "logo": get_logo_base64(document.modele.logo.url),
        "alt_logo": document.modele.logo_alt_text,
        "top_right_text": document.modele.top_right_text.strip(),
        "content": mark_safe(document.content),
    }

    html_string = render_to_string("gsl_notification/pdf/document.html", context)

    pdf_content = HTML(
        string=html_string,
        url_fetcher=django_url_fetcher,
        base_url=settings.STATIC_ROOT,
    ).write_pdf()

    return pdf_content


def merge_documents_into_pdf(
    documents: list[ArreteEtLettreSignes | Annexe],
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

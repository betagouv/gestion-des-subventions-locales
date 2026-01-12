import base64
import io
import os
from functools import lru_cache

import boto3
import img2pdf
import requests
from bs4 import BeautifulSoup
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from pikepdf import Pdf

from gsl import settings
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
    """
    attributes = attribute_path.split(".")
    current_obj = obj
    for attr in attributes:
        current_obj = getattr(current_obj, attr)
    return current_obj


MENTION_TO_ATTRIBUTES = {
    1: {"label": "Nom du bénéficiaire", "attribute": "dossier.ds_demandeur"},
    2: {"label": "Intitulé du projet", "attribute": "dossier.projet_intitule"},
    3: {
        "label": "Nom du département",
        "attribute": "projet.perimetre.departement.name",
    },
    4: {"label": "Montant prévisionnel de la subvention", "attribute": "montant"},
    5: {"label": "Taux de subvention", "attribute": "taux"},
    6: {"label": "Date de commencement", "attribute": "dossier.date_debut"},
    7: {"label": "Date d'achèvement", "attribute": "dossier.date_achevement"},
}


def replace_mentions_in_html(
    htmlContent: str, programmation_projet: ProgrammationProjet
):
    soup = BeautifulSoup(htmlContent, "html.parser")

    for span in soup.find_all("span", class_="mention"):
        id = int(span.get("data-id"))
        if id not in MENTION_TO_ATTRIBUTES:
            raise ValueError(f"Mention {id} inconnue.")
        value = get_nested_attribute(
            programmation_projet,
            MENTION_TO_ATTRIBUTES.get(id)["attribute"],
        )
        if id == 4:
            value = euro(value, 2)
        elif id == 5:
            value = percent(value, 3)
        elif id in [6, 7]:
            value = value.strftime("%d/%m/%Y") if value else "N/A"

        span.replace_with(f"{value}")

    new_text = str(soup)
    return new_text


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

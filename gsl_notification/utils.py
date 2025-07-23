import os

from bs4 import BeautifulSoup
from django.core.files import File
from django.db.models.fields.files import FieldFile

from gsl_core.models import Perimetre
from gsl_core.templatetags.gsl_filters import euro, percent
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import DOTATION_DETR, POSSIBLE_DOTATIONS


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
    file, programmation_projet_id: int
):
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

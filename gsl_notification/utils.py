from bs4 import BeautifulSoup

from gsl_core.models import Perimetre
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
    "Nom du bénéficiaire": "dossier.ds_demandeur",
    "Intitulé du projet": "dossier.projet_intitule",
    "Nom du département": "projet.perimetre.departement.name",
    "Montant prévisionnel de la subvention": "montant",
    "Taux de subvention": "taux",
    "Date de commencement": "dossier.date_debut",
    "Date d'achèvement": "dossier.date_achevement",
}


def replace_mentions_in_html(
    htmlContent: str, programmation_projet: ProgrammationProjet
):
    soup = BeautifulSoup(htmlContent, "html.parser")

    for span in soup.find_all("span", class_="mention"):
        label = span.get("data-label")
        if label not in MENTION_TO_ATTRIBUTES.keys():
            raise ValueError(f"Mention {label} inconnue.")
        value = get_nested_attribute(
            programmation_projet,
            MENTION_TO_ATTRIBUTES[label],
        )
        if label == "Montant prévisionnel de la subvention":
            value = f"{value:,.2f} €".replace(",", " ").replace(".", ",")
        elif label in ["Date de commencement", "Date d'achèvement"]:
            value = value.strftime("%d/%m/%Y") if value else "N/A"
        elif label == "Taux de subvention":
            value = f"{value:,.3f} %".replace(".", ",")

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

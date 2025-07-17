from gsl_core.models import Perimetre
from gsl_projet.constants import DOTATION_DETR, POSSIBLE_DOTATIONS


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

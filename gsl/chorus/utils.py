from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
)

from .models import SuiviFinancier


def resume_dotation(projet, dotation):
    ecritures = SuiviFinancier.objects.filter(
        dn=projet.dossier_ds.ds_number, dotation=dotation
    ).order_by("date_engagement", "ej")
    if not ecritures:
        return None
    montant_accorde = (
        ProgrammationProjet.objects.filter(
            dotation_projet__projet=projet,
            dotation_projet__dotation=dotation,
            status=PROJET_STATUS_ACCEPTED,
        )
        .values_list("montant", flat=True)
        .first()
    )
    montant_engage = sum(ecriture.montant for ecriture in ecritures)
    montant_paye = sum(ecriture.montant for ecriture in ecritures if ecriture.is_paye)
    return {
        "dotation": dotation,
        "ecritures": ecritures,
        "montant_engage": montant_engage,
        "montant_paye": montant_paye,
        "montant_reste": montant_engage - montant_paye,
        "montant_accorde": montant_accorde,
        # Do not consider gap in centimes.
        "has_ecart": montant_accorde is not None
        and abs(montant_engage - montant_accorde) >= 1,
    }


def par_dotation(projet):
    return [
        resume
        for dotation in (DOTATION_DETR, DOTATION_DSIL)
        if (resume := resume_dotation(projet, dotation)) is not None
    ]

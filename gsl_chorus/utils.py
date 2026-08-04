from gsl_chorus.models import SuiviFinancier
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
)


def build_suivi_par_dotation(projet):
    lignes = SuiviFinancier.objects.filter(dn=projet.dossier_ds.ds_number).order_by(
        "date_engagement", "ej"
    )

    accorde_par_dotation = {
        pp.dotation_projet.dotation: pp.montant
        for pp in ProgrammationProjet.objects.filter(
            dotation_projet__projet=projet,
            status=PROJET_STATUS_ACCEPTED,
        ).select_related("dotation_projet")
    }

    par_dotation = []
    for dotation in (DOTATION_DETR, DOTATION_DSIL):
        dot_lignes = [ligne for ligne in lignes if ligne.dotation == dotation]
        if not dot_lignes:
            continue
        engage = sum(ligne.montant for ligne in dot_lignes)
        paye = sum(ligne.montant for ligne in dot_lignes if ligne.is_paye)
        accorde = accorde_par_dotation.get(dotation)
        par_dotation.append(
            {
                "dotation": dotation,
                "lignes": dot_lignes,
                "engage": engage,
                "paye": paye,
                "reste": engage - paye,
                "accorde": accorde,
                "ecart": accorde is not None and abs(engage - accorde) >= 1,
            }
        )
    return par_dotation

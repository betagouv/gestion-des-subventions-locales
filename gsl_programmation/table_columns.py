from django.utils.html import format_html

from gsl_core.table_columns import (
    COLUMN_CATEGORIE,
    COLUMN_DEMANDEUR,
    COLUMN_NUMERO_DN,
    CellLink,
    Column,
    StickyPosition,
    TextAlign,
)
from gsl_core.templatetags.gsl_filters import euro_value, percent, percent_value

COLUMN_INTITULE = Column(
    key="intitule",
    label="Intitulé du projet",
    getter=lambda ctx: ctx["programmation_projet"].projet.dossier_ds.projet_intitule,
    link=CellLink(
        url_getter=lambda ctx: ctx["programmation_projet"].get_absolute_url(),
        fr_link=True,
        keep_querystring=True,
        querystring_extras_getter=lambda ctx: {
            "dotation": ctx["programmation_projet"].dotation
        },
        title_from_value=True,
    ),
    hideable=False,
    sticky=StickyPosition.LEFT_2,
)

COLUMN_COUT_TOTAL = Column(
    key="cout_total",
    label="Coût total du projet (€)",
    getter=lambda ctx: euro_value(ctx["projet"].dossier_ds.finance_cout_total),
    text_align=TextAlign.RIGHT,
)


def _get_montant_taux_demandes(context):
    pp = context.get("programmation_projet")
    montant = pp.projet.dossier_ds.demande_montant if pp else None
    taux = pp.dotation_projet.taux_de_subvention_sollicite if pp else None
    return format_html("{}<br>{}", euro_value(montant), percent(taux))


COLUMN_MONTANT_TAUX_DEMANDES = Column(
    key="montant_taux_demandes",
    label="Montant et taux demandés (€ / %)",
    getter=_get_montant_taux_demandes,
    text_align=TextAlign.RIGHT,
)


def _get_montant_retenu(context):
    pp = context.get("programmation_projet")
    montant = pp.montant if pp else None
    return euro_value(montant)


COLUMN_MONTANT_RETENU = Column(
    key="montant_retenu",
    label="Montant prévisionnel accordé (€)",
    getter=_get_montant_retenu,
    text_align=TextAlign.RIGHT,
)

COLUMN_TAUX = Column(
    key="taux",
    label="Taux de subvention (%)",
    getter=lambda ctx: percent_value(ctx["programmation_projet"].taux),
    text_align=TextAlign.RIGHT,
)

COLUMN_DOCUMENTS = Column(
    key="documents",
    label="Documents ajoutés",
    template_name="gsl_programmation/table_cells/documents.html",
)

COLUMN_STATUT = Column(
    key="statut",
    label="Statut",
    getter=lambda ctx: ctx["programmation_projet"].get_status_display(),
    sticky=StickyPosition.RIGHT_1,
)

COLUMN_NOTIFICATION = Column(
    key="notification",
    label="Notification",
    template_name="gsl_programmation/table_cells/notification.html",
    sticky=StickyPosition.RIGHT_2,
)

PROGRAMMATION_TABLE_COLUMNS = (
    COLUMN_INTITULE,
    COLUMN_NUMERO_DN,
    COLUMN_DEMANDEUR,
    COLUMN_COUT_TOTAL,
    COLUMN_MONTANT_TAUX_DEMANDES,
    COLUMN_MONTANT_RETENU,
    COLUMN_TAUX,
    COLUMN_CATEGORIE,
    COLUMN_DOCUMENTS,
    COLUMN_STATUT,
    COLUMN_NOTIFICATION,
)

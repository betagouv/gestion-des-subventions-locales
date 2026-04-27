from django.utils.html import format_html

from gsl_core.table_columns import (
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_1,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_2,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_3,
    COLUMN_ARRONDISSEMENT,
    COLUMN_BUDGET_VERT_DEMANDEUR,
    COLUMN_BUDGET_VERT_INSTRUCTEUR,
    COLUMN_COFINANCEMENTS,
    COLUMN_COMMENT_1,
    COLUMN_COMMENT_2,
    COLUMN_COMMENT_3,
    COLUMN_COMPLETED_DOSSIER,
    COLUMN_CONTRACTUALISATION,
    COLUMN_DATE_DEBUT_PROJET,
    COLUMN_DATE_DEPOT,
    COLUMN_DATE_FIN_PROJET,
    COLUMN_DEMANDEUR,
    COLUMN_DOTATIONS_SOLLICITEES,
    COLUMN_EPCI,
    COLUMN_INTITULE,
    COLUMN_NOM_DEMANDEUR,
    COLUMN_NOTIFICATION,
    COLUMN_NUMERO_DN,
    COLUMN_PRIORITY,
    COLUMN_ZONAGE,
    Column,
    ColumnWidth,
    StickyPosition,
    TextAlign,
    get_categorie,
)
from gsl_core.templatetags.gsl_filters import euro_value, percent_value

COLUMN_DOTATION = Column(
    key="dotation",
    label="Dotation",
    getter=lambda ctx: ctx["dotation_projet"].dotation,
    per_dotation=True,
)

COLUMN_COUT_TOTAL = Column(
    key="cout_total",
    label="Coût total du projet (€)",
    getter=lambda ctx: euro_value(ctx["projet"].dossier_ds.finance_cout_total),
    text_align=TextAlign.RIGHT,
    aggregate_key="total_cost",
    sort_param="cout",
)

COLUMN_MONTANT_SOLLICITE = Column(
    key="montant_sollicite",
    label="Montant sollicité (€)",
    getter=lambda ctx: euro_value(ctx["projet"].dossier_ds.demande_montant),
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_asked",
    sort_param="montant_sollicite",
)

COLUMN_ASSIETTE = Column(
    key="assiette",
    label="Assiette (€)",
    getter=lambda ctx: euro_value(ctx["dotation_projet"].assiette),
    per_dotation=True,
    text_align=TextAlign.RIGHT,
    sort_param="assiette",
)

COLUMN_MONTANT_RETENU = Column(
    key="montant_retenu",
    label="Montant retenu (€)",
    getter=lambda ctx: euro_value(ctx["dotation_projet"].montant_retenu),
    per_dotation=True,
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_granted",
    sort_param="montant_retenu",
)

COLUMN_TAUX = Column(
    key="taux",
    label="Taux de subvention (%)",
    getter=lambda ctx: percent_value(ctx["dotation_projet"].taux_retenu, 2),
    per_dotation=True,
    text_align=TextAlign.RIGHT,
    header_help_text="Le taux de subvention est calculé en fonction de l'assiette (ou du coût total du projet si l'assiette n'est pas renseignée) et du montant retenu.",
    width=ColumnWidth.MIN_105,
    sort_param="taux",
)

COLUMN_CATEGORIE = Column(
    key="categorie",
    label="Catégorie d'opération",
    getter=get_categorie,
    max_3_lines=True,
    per_dotation=True,
    width=ColumnWidth.MIN_180,
)


def _get_projet_statut(context):
    dp = context.get("dotation_projet")
    if not dp:
        return ""
    return format_html(
        '<span class="projet_status__{}">{}</span>',
        dp.status,
        dp.get_status_display(),
    )


COLUMN_STATUT = Column(
    key="statut",
    label="Statut",
    getter=_get_projet_statut,
    per_dotation=True,
    sticky=StickyPosition.RIGHT_1,
)

PROJET_TABLE_COLUMNS = (
    COLUMN_DATE_DEPOT,
    COLUMN_INTITULE,
    COLUMN_NUMERO_DN,
    COLUMN_DEMANDEUR,
    COLUMN_ARRONDISSEMENT,
    COLUMN_EPCI,
    COLUMN_NOM_DEMANDEUR,
    COLUMN_DOTATIONS_SOLLICITEES,
    COLUMN_DATE_DEBUT_PROJET,
    COLUMN_DATE_FIN_PROJET,
    COLUMN_BUDGET_VERT_DEMANDEUR,
    COLUMN_BUDGET_VERT_INSTRUCTEUR,
    COLUMN_COFINANCEMENTS,
    COLUMN_ZONAGE,
    COLUMN_CONTRACTUALISATION,
    COLUMN_DOTATION,
    COLUMN_COUT_TOTAL,
    COLUMN_MONTANT_SOLLICITE,
    COLUMN_ASSIETTE,
    COLUMN_MONTANT_RETENU,
    COLUMN_TAUX,
    COLUMN_CATEGORIE,
    COLUMN_COMPLETED_DOSSIER,
    COLUMN_PRIORITY,
    COLUMN_COMMENT_1,
    COLUMN_COMMENT_2,
    COLUMN_COMMENT_3,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_1,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_2,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_3,
    COLUMN_STATUT,
    COLUMN_NOTIFICATION,
)

SANS_PIECES_SKIP_KEYS = {"cout_total", "montant_sollicite"}

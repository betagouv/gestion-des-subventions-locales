from django.utils.html import format_html

from gsl_core.table_columns import (
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_1,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_2,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_3,
    COLUMN_ARRONDISSEMENT,
    COLUMN_BUDGET_VERT_DEMANDEUR,
    COLUMN_BUDGET_VERT_INSTRUCTEUR,
    COLUMN_CATEGORIE,
    COLUMN_COFINANCEMENTS,
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
    COLUMN_NUMERO_DN,
    COLUMN_ZONAGE,
    Column,
    StickyPosition,
    TextAlign,
)
from gsl_core.templatetags.gsl_filters import euro_value, percent, percent_value

COLUMN_DOTATION = Column(
    key="dotation",
    label="Dotation",
    template_name="gsl_simulation/table_cells/dotation.html",
)

COLUMN_COUT_TOTAL = Column(
    key="cout_total",
    label="Coût total du projet (€)",
    getter=lambda ctx: euro_value(ctx["projet"].dossier_ds.finance_cout_total, 2),
    text_align=TextAlign.RIGHT,
    aggregate_key="total_cost",
    sort_param="cout",
)


def _get_montant_sollicite(context):
    projet = context.get("projet")
    montant = projet.dossier_ds.demande_montant if projet else None
    dp = context.get("dotation_projet")
    taux = dp.taux_de_subvention_sollicite if dp else None
    return format_html("{}<br>{}", euro_value(montant, 2), percent(taux, 2))


COLUMN_MONTANT_SOLLICITE = Column(
    key="montant_sollicite",
    label="Montant sollicité (€)",
    getter=_get_montant_sollicite,
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_asked",
    sort_param="montant_sollicite",
)


def _get_other_dotation_assiette(context):
    dp = context["other_dotation"]
    return euro_value(dp.assiette, 2)


def _get_simu_other_dotation_montant(context):
    dp = context["other_dotation"]
    simu = dp.last_updated_simulation_projet
    if not simu:
        return "—"
    return format_html("<b>{}</b>", euro_value(simu.montant, 2))


def _get_simu_other_dotation_taux(context):
    dp = context["other_dotation"]
    simu = dp.last_updated_simulation_projet
    if not simu:
        return "—"
    return format_html("<b>{}</b>", percent_value(simu.taux, 2))


def _get_simu_other_dotation_statut(context):
    dp = context["other_dotation"]
    simu = dp.last_updated_simulation_projet
    if not simu:
        return ""
    return format_html(
        '<div class="gsl-projet-table__status-notified">{}</div>',
        simu.get_status_display(),
    )


COLUMN_ASSIETTE = Column(
    key="assiette",
    label="Assiette (€)",
    template_name="gsl_simulation/table_cells/assiette.html",
    other_dotation_getter=_get_other_dotation_assiette,
    text_align=TextAlign.RIGHT,
    sort_param="assiette",
)

COLUMN_MONTANT_RETENU = Column(
    key="montant_retenu",
    label="Montant prévisionnel accordé (€)",
    template_name="gsl_simulation/table_cells/montant_retenu.html",
    other_dotation_getter=_get_simu_other_dotation_montant,
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_granted",
    aggregate_id="total-amount-granted",
    sort_param="montant_previsionnel",
)

COLUMN_TAUX = Column(
    key="taux",
    label="Taux (%)",
    template_name="gsl_simulation/table_cells/taux.html",
    other_dotation_getter=_get_simu_other_dotation_taux,
    text_align=TextAlign.RIGHT,
    header_help_text="Le taux de subvention est calculé en fonction de l'assiette si elle est renseignée, sinon il est calculé en fonction du coût total du projet.",
    sort_param="taux",
)

COLUMN_STATUT = Column(
    key="statut",
    label="Statut",
    template_name="gsl_simulation/table_cells/statut.html",
    other_dotation_getter=_get_simu_other_dotation_statut,
    sticky=StickyPosition.RIGHT_1,
)

COLUMN_NOTIFICATION = Column(
    key="notification",
    label="Notification",
    template_name="gsl_core/table_cells/notification.html",
    sticky=StickyPosition.RIGHT_2,
)


COLUMN_COMMENT_1 = Column(
    key="comment_1",
    label="Commentaire 1",
    getter=lambda ctx: ctx["projet"].comment_1,
    template_name="gsl_simulation/table_cells/comment.html",
    displayed_by_default=False,
)

COLUMN_COMMENT_2 = Column(
    key="comment_2",
    label="Commentaire 2",
    getter=lambda ctx: ctx["projet"].comment_2,
    template_name="gsl_simulation/table_cells/comment.html",
    displayed_by_default=False,
)

COLUMN_COMMENT_3 = Column(
    key="comment_3",
    label="Commentaire 3",
    getter=lambda ctx: ctx["projet"].comment_3,
    template_name="gsl_simulation/table_cells/comment.html",
    displayed_by_default=False,
)


SIMULATION_TABLE_COLUMNS = (
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
    COLUMN_COMMENT_1,
    COLUMN_COMMENT_2,
    COLUMN_COMMENT_3,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_1,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_2,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_3,
    COLUMN_STATUT,
    COLUMN_NOTIFICATION,
)

from django.utils.html import format_html

from gsl_core.table_columns import (
    COLUMN_CATEGORIE,
    COLUMN_DATE_DEPOT,
    COLUMN_DEMANDEUR,
    COLUMN_INTITULE,
    COLUMN_NUMERO_DN,
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
    label="Coût total du projet (€)",
    getter=lambda ctx: euro_value(ctx["projet"].dossier_ds.finance_cout_total, 2),
    text_align=TextAlign.RIGHT,
    aggregate_key="total_cost",
)


def _get_montant_sollicite(context):
    projet = context.get("projet")
    montant = projet.dossier_ds.demande_montant if projet else None
    dp = context.get("dotation_projet")
    taux = dp.taux_de_subvention_sollicite if dp else None
    return format_html("{}<br>{}", euro_value(montant, 2), percent(taux))


COLUMN_MONTANT_SOLLICITE = Column(
    key="montant_sollicite",
    label="Montant sollicité (€)",
    getter=_get_montant_sollicite,
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_asked",
)


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
    return format_html("<b>{}</b>", percent_value(simu.taux))


def _get_simu_other_dotation_statut(context):
    dp = context["other_dotation"]
    simu = dp.last_updated_simulation_projet
    if not simu:
        return ""
    return format_html(
        '<div class="gsl-projet-table__status-notified">{}</div>',
        simu.get_status_display(),
    )


COLUMN_MONTANT_RETENU = Column(
    key="montant_retenu",
    label="Montant prévisionnel accordé (€)",
    template_name="gsl_simulation/table_cells/montant_retenu.html",
    other_dotation_getter=_get_simu_other_dotation_montant,
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_granted",
    aggregate_id="total-amount-granted",
)

COLUMN_TAUX = Column(
    key="taux",
    label="Taux de subvention (%)",
    template_name="gsl_simulation/table_cells/taux.html",
    other_dotation_getter=_get_simu_other_dotation_taux,
    text_align=TextAlign.RIGHT,
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

SIMULATION_TABLE_COLUMNS = (
    COLUMN_DATE_DEPOT,
    COLUMN_INTITULE,
    COLUMN_NUMERO_DN,
    COLUMN_DEMANDEUR,
    COLUMN_DOTATION,
    COLUMN_COUT_TOTAL,
    COLUMN_MONTANT_SOLLICITE,
    COLUMN_MONTANT_RETENU,
    COLUMN_TAUX,
    COLUMN_CATEGORIE,
    COLUMN_STATUT,
    COLUMN_NOTIFICATION,
)

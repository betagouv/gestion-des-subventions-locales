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
from gsl_core.templatetags.gsl_filters import euro_value, percent

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

COLUMN_MONTANT_RETENU = Column(
    key="montant_retenu",
    label="Montant prévisionnel accordé (€)",
    template_name="gsl_simulation/table_cells/montant_retenu.html",
    text_align=TextAlign.RIGHT,
    aggregate_key="total_amount_granted",
    aggregate_id="total-amount-granted",
)

COLUMN_TAUX = Column(
    key="taux",
    label="Taux de subvention (%)",
    template_name="gsl_simulation/table_cells/taux.html",
    text_align=TextAlign.RIGHT,
)

COLUMN_STATUT = Column(
    key="statut",
    label="Statut",
    template_name="gsl_simulation/table_cells/statut.html",
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

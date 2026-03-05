from django.utils.html import format_html

from gsl_core.table_columns import (
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_1,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_2,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_3,
    COLUMN_ARRONDISSEMENT,
    COLUMN_BUDGET_VERT_DEMANDEUR,
    COLUMN_BUDGET_VERT_INSTRUCTEUR,
    COLUMN_CATEGORIE,
    COLUMN_COMMENT_1,
    COLUMN_COMMENT_2,
    COLUMN_COMMENT_3,
    COLUMN_COMPLETED_DOSSIER,
    COLUMN_DATE_DEBUT_PROJET,
    COLUMN_DATE_FIN_PROJET,
    COLUMN_DEMANDEUR,
    COLUMN_DOTATIONS_SOLLICITEES,
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
    other_dotation_getter=lambda ctx: f"Informations pour la dotation {ctx['other_dotation'].dotation}",
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
    return format_html("{}<br>{}", euro_value(montant), percent(taux, 2))


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


def _get_other_dotation_assiette(context):
    dp = context["other_dotation"]
    return euro_value(dp.assiette, 2)


def _get_other_dotation_montant_retenu(context):
    dp = context["other_dotation"]
    simu = dp.last_updated_simulation_projet
    return euro_value(simu.montant, 2) if simu else "—"


def _get_other_dotation_taux(context):
    dp = context["other_dotation"]
    simu = dp.last_updated_simulation_projet
    return percent_value(simu.taux, 2) if simu else "—"


def _get_other_dotation_documents(context):
    dp = context["other_dotation"]
    if not hasattr(dp, "programmation_projet"):
        return ""
    documents = dp.programmation_projet.documents_summary
    if not documents:
        return ""
    items = "".join(format_html("<li>{}</li>", doc) for doc in documents)
    return format_html("<ul>{}</ul>", items)


def _get_other_dotation_statut(context):
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
    label="Assiette (€)",
    getter=lambda ctx: euro_value(ctx["programmation_projet"].dotation_projet.assiette),
    other_dotation_getter=_get_other_dotation_assiette,
    text_align=TextAlign.RIGHT,
)

COLUMN_MONTANT_RETENU = Column(
    key="montant_retenu",
    label="Montant prévisionnel accordé (€)",
    getter=_get_montant_retenu,
    other_dotation_getter=_get_other_dotation_montant_retenu,
    text_align=TextAlign.RIGHT,
)

COLUMN_TAUX = Column(
    key="taux",
    label="Taux de subvention (%)",
    getter=lambda ctx: percent_value(ctx["programmation_projet"].taux, 2),
    other_dotation_getter=_get_other_dotation_taux,
    text_align=TextAlign.RIGHT,
)

COLUMN_DOCUMENTS = Column(
    key="documents",
    label="Documents ajoutés",
    template_name="gsl_programmation/table_cells/documents.html",
    other_dotation_getter=_get_other_dotation_documents,
)

COLUMN_STATUT = Column(
    key="statut",
    label="Statut",
    getter=lambda ctx: ctx["programmation_projet"].get_status_display(),
    other_dotation_getter=_get_other_dotation_statut,
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
    COLUMN_ARRONDISSEMENT,
    COLUMN_DOTATIONS_SOLLICITEES,
    COLUMN_DATE_DEBUT_PROJET,
    COLUMN_DATE_FIN_PROJET,
    COLUMN_BUDGET_VERT_DEMANDEUR,
    COLUMN_BUDGET_VERT_INSTRUCTEUR,
    COLUMN_COUT_TOTAL,
    COLUMN_MONTANT_TAUX_DEMANDES,
    COLUMN_ASSIETTE,
    COLUMN_MONTANT_RETENU,
    COLUMN_TAUX,
    COLUMN_CATEGORIE,
    COLUMN_COMPLETED_DOSSIER,
    COLUMN_DOCUMENTS,
    COLUMN_COMMENT_1,
    COLUMN_COMMENT_2,
    COLUMN_COMMENT_3,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_1,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_2,
    COLUMN_ANNOTATIONS_CHAMP_LIBRE_3,
    COLUMN_STATUT,
    COLUMN_NOTIFICATION,
)

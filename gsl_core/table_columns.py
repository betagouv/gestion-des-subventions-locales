from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from django.utils.html import mark_safe

from gsl_core.templatetags.gsl_filters import euro_value
from gsl_demarches_simplifiees.models import Dossier


class StickyPosition(Enum):
    LEFT_1 = "left-1"
    LEFT_2 = "left-2"
    LEFT_3 = "left-3"
    RIGHT_1 = "right-1"
    RIGHT_2 = "right-2"


class TextAlign(Enum):
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"


COMMON_CELL_TEMPLATE = "gsl_core/table_cells/_common_cell.html"


@dataclass(frozen=True)
class CellLink:
    url_getter: Callable
    fr_link: bool = False
    new_tab: bool = False
    nowrap: bool = False
    title: Optional[str] = None
    title_from_value: bool = False
    keep_querystring: bool = False
    # Callable receiving context, returns dict of extra querystring params
    querystring_extras_getter: Optional[Callable] = None

    @property
    def resolved_title(self) -> str:
        if not self.title:
            return ""
        if self.new_tab:
            return f"{self.title} - nouvelle fenêtre"
        return self.title

    @property
    def css_classes(self) -> str:
        parts = []
        if self.fr_link:
            parts.append("fr-link")
        if self.nowrap:
            parts.append("gsl-nowrap")
        return " ".join(parts)


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    template_name: str = ""

    # Getter-based rendering (alternative to template_name)
    getter: Optional[Callable] = None

    # Other-dotation row rendering: receives context with "other_dotation"
    other_dotation_getter: Optional[Callable] = None

    # Link rendering (alternative to custom template for linked values)
    link: Optional[CellLink] = None

    # Per-dotation rendering: row template loops over dotation_projets
    per_dotation: bool = False

    # Styling
    text_align: Optional[TextAlign] = None
    max_3_lines: bool = False
    linebreaks: bool = False

    # Column visibility toggle
    hideable: bool = True
    displayed_by_default: Optional[bool] = True

    # Existing fields
    sticky: Optional[StickyPosition] = None
    aggregate_key: Optional[str] = None
    aggregate_id: Optional[str] = None
    header_template_name: Optional[str] = None
    header_help_text: Optional[str] = None

    def __post_init__(self):
        if not self.template_name and not self.getter:
            raise ValueError(
                f"Column '{self.key}' must have either template_name or getter"
            )

    @property
    def resolved_template_name(self) -> str:
        return self.template_name or COMMON_CELL_TEMPLATE

    @property
    def css_key(self) -> str:
        return self.key.replace("_", "-")

    @property
    def css_class(self) -> str:
        return f"gsl-col--{self.css_key}"

    @property
    def sticky_class(self) -> str:
        if self.sticky is None:
            return ""
        return f"gsl-projet-table__sticky-{self.sticky.value}"

    @property
    def align_class(self) -> str:
        if self.text_align == TextAlign.RIGHT:
            return "gsl-money"
        if self.text_align == TextAlign.CENTER:
            return "fr-cell--center"
        return ""

    @property
    def th_classes(self) -> str:
        return " ".join(filter(None, [self.css_class, self.sticky_class]))

    @property
    def td_classes(self) -> str:
        return " ".join(
            filter(None, [self.css_class, self.sticky_class, self.align_class])
        )

    @property
    def has_other_dotation_getter(self) -> bool:
        return self.other_dotation_getter is not None


# Shared column instances used across multiple tables


# Lazy import to avoid circular dependency
def _format_demandeur_nom(name):
    from gsl_core.templatetags.gsl_filters import format_demandeur_nom

    return format_demandeur_nom(name)


COLUMN_INTITULE = Column(
    key="intitule",
    label="Intitulé du projet",
    getter=lambda ctx: ctx["projet"].dossier_ds.projet_intitule,
    other_dotation_getter=lambda ctx: (
        f"Informations pour la dotation {ctx['other_dotation'].dotation}"
    ),
    link=CellLink(
        url_getter=lambda ctx: ctx["row_url"],
        fr_link=True,
        keep_querystring=True,
        title_from_value=True,
    ),
    hideable=False,
    sticky=StickyPosition.LEFT_2,
)

COLUMN_NUMERO_DN = Column(
    key="numero_dn",
    label="N° D.N.",
    getter=lambda ctx: ctx["projet"].dossier_ds.ds_number,
    link=CellLink(
        url_getter=lambda ctx: ctx["projet"].dossier_ds.url_on_ds,
        new_tab=True,
        nowrap=True,
        title="Voir le dossier sur Démarche Numérique",
    ),
    sticky=StickyPosition.LEFT_3,
)

COLUMN_DEMANDEUR = Column(
    key="demandeur",
    label="Demandeur",
    getter=lambda ctx: _format_demandeur_nom(ctx["projet"].demandeur.name),
    max_3_lines=True,
)

COLUMN_NOTIFICATION = Column(
    key="notification",
    label="Notification",
    template_name="gsl_core/table_cells/notification.html",
    sticky=StickyPosition.RIGHT_2,
)


def _categorie_for_dotation_projet(dotation_projet):
    if not dotation_projet:
        return ""
    dotation = dotation_projet.dotation
    dossier_ds = dotation_projet.projet.dossier_ds
    if dotation == "DSIL":
        categorie = getattr(dossier_ds, "demande_categorie_dsil", None)
        return categorie.label if categorie else ""
    if dotation == "DETR":
        if getattr(dossier_ds, "demande_has_categorie_detr", None) is False:
            return "Hors catégorie"
        categorie = getattr(dossier_ds, "demande_categorie_detr", None)
        return categorie.complete_label if categorie else ""
    return ""


def get_categorie(context):
    return _categorie_for_dotation_projet(context.get("dotation_projet"))


COLUMN_CATEGORIE = Column(
    key="categorie",
    label="Catégorie d'opération",
    getter=get_categorie,
    other_dotation_getter=lambda ctx: _categorie_for_dotation_projet(
        ctx["other_dotation"]
    ),
    max_3_lines=True,
)

COLUMN_DATE_DEPOT = Column(
    key="date_depot",
    label="Date de dépôt",
    template_name="gsl_core/table_cells/date_depot.html",
    sticky=StickyPosition.LEFT_1,
    text_align=TextAlign.CENTER,
)

COLUMN_DOTATIONS_SOLLICITEES = Column(
    key="dotations_sollicitees",
    label="Dotations sollicitées",
    getter=lambda ctx: " et ".join(ctx["projet"].dossier_ds.dotations_demande),
    displayed_by_default=False,
)


def _format_date_or_dash(date):
    return date.strftime("%d/%m/%Y") if date else "—"


COLUMN_DATE_DEBUT_PROJET = Column(
    key="date_debut_projet",
    label="Date de commencement de l'opération",
    getter=lambda ctx: _format_date_or_dash(ctx["projet"].dossier_ds.date_debut),
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
)

COLUMN_DATE_FIN_PROJET = Column(
    key="date_achevement",
    label="Date prévisionnelle d'achèvement de l'opération",
    getter=lambda ctx: _format_date_or_dash(ctx["projet"].dossier_ds.date_achevement),
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
)

COLUMN_ARRONDISSEMENT = Column(
    key="arrondissement",
    label="Arrondissement",
    getter=lambda ctx: (
        "-"
        if ctx["projet"].dossier_ds.porteur_de_projet_arrondissement is None
        else ctx["projet"].dossier_ds.porteur_de_projet_arrondissement.name
    ),
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
)

COLUMN_NOM_DEMANDEUR = Column(
    key="nom_demandeur",
    label="Nom du demandeur",
    getter=lambda ctx: ctx["projet"].dossier_ds.porteur_fullname,
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
)

COLUMN_BUDGET_VERT_DEMANDEUR = Column(
    key="budget_vert_demandeur",
    label="Budget vert (demandeur)",
    getter=lambda ctx: ctx["projet"].dossier_ds.environnement_transition_eco,
    template_name="gsl_core/table_cells/_yes_no_cell.html",
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
)

COLUMN_BUDGET_VERT_INSTRUCTEUR = Column(
    key="budget_vert_instructeur",
    label="Budget vert (instructeur)",
    getter=lambda ctx: ctx["projet"].is_budget_vert,
    template_name="gsl_core/table_cells/_yes_no_cell.html",
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
)


def _get_cofinancements(context):
    dossier = context["projet"].dossier_ds
    cofinancements = dossier.get_cofinancements_avec_montants()
    if not cofinancements:
        return "—"
    lignes = []
    for cofinancement in cofinancements:
        if cofinancement["montant"]:
            ligne = f"{cofinancement['nom']} : {euro_value(cofinancement['montant'])}€"
        else:
            ligne = cofinancement["nom"]
        lignes.append(ligne)
    return mark_safe("<ul><li>" + "</li><li>".join(lignes) + "</li></ul>")


COLUMN_COFINANCEMENTS = Column(
    key="cofinancements",
    label="Co-financements sollicités",
    getter=_get_cofinancements,
    displayed_by_default=False,
)


COLUMN_COMPLETED_DOSSIER = Column(
    key="completed_dossier",
    label="Dossier complet",
    getter=lambda ctx: (
        ctx["projet"].dossier_ds.ds_state != Dossier.STATE_EN_CONSTRUCTION
    ),
    template_name="gsl_core/table_cells/_yes_no_cell.html",
    displayed_by_default=False,
    text_align=TextAlign.CENTER,
    header_help_text="Non complet signifie que le dossier est en construction sur DN.",
)

COLUMN_COMMENT_1 = Column(
    key="comment_1",
    label="Commentaire 1",
    getter=lambda ctx: ctx["projet"].comment_1,
    displayed_by_default=False,
    max_3_lines=True,
    linebreaks=True,
)

COLUMN_COMMENT_2 = Column(
    key="comment_2",
    label="Commentaire 2",
    getter=lambda ctx: ctx["projet"].comment_2,
    displayed_by_default=False,
    max_3_lines=True,
    linebreaks=True,
)

COLUMN_COMMENT_3 = Column(
    key="comment_3",
    label="Commentaire 3",
    getter=lambda ctx: ctx["projet"].comment_3,
    displayed_by_default=False,
    max_3_lines=True,
    linebreaks=True,
)

COLUMN_ANNOTATIONS_CHAMP_LIBRE_1 = Column(
    key="annotations_champ_libre_1",
    label="Annotations DN 1",
    getter=lambda ctx: ctx["projet"].dossier_ds.annotations_champ_libre_1,
    displayed_by_default=False,
    max_3_lines=True,
    linebreaks=True,
)

COLUMN_ANNOTATIONS_CHAMP_LIBRE_2 = Column(
    key="annotations_champ_libre_2",
    label="Annotations DN 2",
    getter=lambda ctx: ctx["projet"].dossier_ds.annotations_champ_libre_2,
    displayed_by_default=False,
    max_3_lines=True,
    linebreaks=True,
)

COLUMN_ANNOTATIONS_CHAMP_LIBRE_3 = Column(
    key="annotations_champ_libre_3",
    label="Annotations DN 3",
    getter=lambda ctx: ctx["projet"].dossier_ds.annotations_champ_libre_3,
    displayed_by_default=False,
    max_3_lines=True,
    linebreaks=True,
)

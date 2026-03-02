from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from django.template.defaultfilters import date as date_filter
from django.utils.html import format_html


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

    # Link rendering (alternative to custom template for linked values)
    link: Optional[CellLink] = None

    # Per-dotation rendering: row template loops over dotation_projets
    per_dotation: bool = False

    # Styling
    text_align: Optional[TextAlign] = None
    max_3_lines: bool = False

    # Existing fields
    sticky: Optional[StickyPosition] = None
    aggregate_key: Optional[str] = None
    aggregate_id: Optional[str] = None
    header_template_name: Optional[str] = None

    def __post_init__(self):
        if not self.template_name and not self.getter:
            raise ValueError(
                f"Column '{self.key}' must have either template_name or getter"
            )

    @property
    def resolved_template_name(self) -> str:
        return self.template_name or COMMON_CELL_TEMPLATE

    @property
    def css_class(self) -> str:
        return f"gsl-col--{self.key.replace('_', '-')}"

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


# Shared column instances used across multiple tables


# Lazy import to avoid circular dependency
def _format_demandeur_nom(name):
    from gsl_core.templatetags.gsl_filters import format_demandeur_nom

    return format_demandeur_nom(name)


COLUMN_INTITULE = Column(
    key="intitule",
    label="Intitulé du projet",
    getter=lambda ctx: ctx["projet"].dossier_ds.projet_intitule,
    link=CellLink(
        url_getter=lambda ctx: ctx["row_url"],
        fr_link=True,
        keep_querystring=True,
        title_from_value=True,
    ),
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


def get_categorie(context):
    dotation_projet = context.get("dotation_projet")
    if not dotation_projet:
        return ""
    dotation = dotation_projet.dotation
    projet = context.get("projet")
    if not projet:
        return ""
    dossier_ds = projet.dossier_ds
    if dotation == "DSIL":
        categorie = getattr(dossier_ds, "demande_categorie_dsil", None)
        return categorie.label if categorie else ""
    if dotation == "DETR":
        if getattr(dossier_ds, "demande_has_categorie_detr", None) is False:
            return "Hors catégorie"
        categorie = getattr(dossier_ds, "demande_categorie_detr", None)
        return categorie.complete_label if categorie else ""
    return ""


COLUMN_CATEGORIE = Column(
    key="categorie",
    label="Catégorie d'opération",
    getter=get_categorie,
    max_3_lines=True,
)

REPORTE_TAG = (
    '<span class="fr-tag fr-tag--sm fr-tag--icon-left'
    ' fr-icon-arrow-turn-back-line fr-mt-0-5v">Reporté</span>'
)


def _get_date_depot(context):
    dossier = context["projet"].dossier_ds
    formatted = date_filter(dossier.ds_date_depot, "d/m/Y")
    if dossier.demande_numero_demande_precedente:
        return format_html("{} " + REPORTE_TAG, formatted)
    return formatted


COLUMN_DATE_DEPOT = Column(
    key="date_depot",
    label="Date de dépôt",
    getter=_get_date_depot,
    sticky=StickyPosition.LEFT_1,
    text_align=TextAlign.CENTER,
)

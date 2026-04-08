from import_export.resources import Field, ModelResource
from import_export.widgets import (
    BooleanWidget,
    DateTimeWidget,
    DateWidget,
    Widget,
)

from gsl_demarches_simplifiees.models import Dossier
from gsl_simulation.models import SimulationProjet

# Mapping from table Column.css_key → resource field name (1:1)
CSS_KEY_TO_RESOURCE_FIELDS = {
    "date-depot": "date_depot",
    "intitule": "projet_intitule",
    "numero-dn": "dossier_number",
    "demandeur": "demandeur_name",
    "arrondissement": "arrondissement",
    "dotations-sollicitees": "has_double_dotations",
    "date-debut-projet": "date_debut",
    "date-achevement": "date_achevement",
    "budget-vert-demandeur": "budget_vert_demandeur",
    "budget-vert-instructeur": "is_budget_vert",
    "dotation": "dotation",
    "cout-total": "cout_total",
    "montant-sollicite": "demande_montant",
    "assiette": "assiette",
    "montant-retenu": "montant",
    "taux": "taux",
    "categorie": "categorie",
    "completed-dossier": "completed_dossier",
    "comment-1": "comment_1",
    "comment-2": "comment_2",
    "comment-3": "comment_3",
    "annotations-champ-libre-1": "champ_libre_1",
    "annotations-champ-libre-2": "champ_libre_2",
    "annotations-champ-libre-3": "champ_libre_3",
    "statut": "status",
    "nom-demandeur": "porteur_name",
}


class TauxWidget(Widget):
    def __init__(self, fmt=None):
        self.fmt = fmt

    def render(self, value, obj=None, **kwargs):
        if value is None:
            return ""
        if self.fmt == "csv":
            return f"{float(value):.4f}".replace(".", ",")
        return round(float(value), 4)


class DecimalWidget(Widget):
    def __init__(self, fmt=None):
        self.fmt = fmt

    def render(self, value, obj=None, **kwargs):
        if value is None:
            return ""
        if self.fmt == "csv":
            return f"{float(value):.2f}".replace(".", ",")
        return round(float(value), 2)


class OuiNonWidget(BooleanWidget):
    def render(self, value, obj=None, **kwargs):
        if value is None:
            return "Inconnu"
        return "Oui" if value else "Non"


class BaseSimulationProjetResource(ModelResource):
    def __init__(self, export_format=None):
        super().__init__()
        for field in self.fields.values():
            if isinstance(field.widget, (DecimalWidget, TauxWidget)):
                field.widget.fmt = export_format

    # --- Fields mapped to table columns (subject to column visibility filtering) ---

    date_depot = Field(
        attribute="projet__dossier_ds__ds_date_depot",
        column_name="Date de dépôt du dossier",
        widget=DateTimeWidget(format="%d/%m/%Y"),
    )
    dossier_number = Field(
        attribute="projet__dossier_ds__ds_number",
        column_name="Numéro de dossier DS",
    )
    projet_intitule = Field(
        attribute="projet__dossier_ds__projet_intitule",
        column_name="Intitulé du projet",
    )
    demandeur_name = Field(
        attribute="projet__demandeur__name",
        column_name="Demandeur",
    )
    arrondissement = Field(
        attribute="projet__demandeur__address__commune__arrondissement__name",
        column_name="Arrondissement du demandeur",
    )
    has_double_dotations = Field(
        attribute="projet__has_double_dotations",
        column_name="Projet en double dotation",
        widget=OuiNonWidget(),
    )
    cout_total = Field(
        attribute="projet__dossier_ds__finance_cout_total",
        column_name="Coût total du projet",
        widget=DecimalWidget(),
    )
    assiette = Field(
        attribute="dotation_projet__assiette",
        column_name="Assiette subventionnable",
        widget=DecimalWidget(),
    )
    demande_montant = Field(
        attribute="projet__dossier_ds__demande_montant",
        column_name="Montant demandé",
        widget=DecimalWidget(),
    )
    demande_taux = Field(
        attribute="dotation_projet__taux_de_subvention_sollicite",
        column_name="Taux demandé",
        widget=TauxWidget(),
    )
    status = Field(
        attribute="get_status_display",
        column_name="Statut de la simulation",
    )
    montant = Field(
        attribute="montant",
        column_name="Montant prévisionnel accordé",
        widget=DecimalWidget(),
    )
    taux = Field(
        attribute="taux",
        column_name="Taux prévisionnel accordé",
        widget=TauxWidget(),
    )
    date_debut = Field(
        attribute="projet__dossier_ds__date_debut",
        column_name="Date de début des travaux",
        widget=DateWidget(format="%d/%m/%Y"),
    )
    date_achevement = Field(
        attribute="projet__dossier_ds__date_achevement",
        column_name="Date de fin des travaux",
        widget=DateWidget(format="%d/%m/%Y"),
    )
    budget_vert_demandeur = Field(
        attribute="projet__dossier_ds__environnement_transition_eco",
        column_name="Budget vert (demandeur)",
        widget=OuiNonWidget(),
    )
    is_budget_vert = Field(
        attribute="projet__is_budget_vert",
        column_name="Projet concourant à la transition écologique",
        widget=OuiNonWidget(),
    )
    dotation = Field(
        attribute="dotation_projet__dotation",
        column_name="Dotation",
    )
    categorie = Field(
        column_name="Catégorie d'opération",
    )
    completed_dossier = Field(
        column_name="Dossier complet",
    )
    comment_1 = Field(
        attribute="projet__comment_1",
        column_name="Commentaire 1",
    )
    comment_2 = Field(
        attribute="projet__comment_2",
        column_name="Commentaire 2",
    )
    comment_3 = Field(
        attribute="projet__comment_3",
        column_name="Commentaire 3",
    )
    champ_libre_1 = Field(
        attribute="projet__dossier_ds__annotations_champ_libre_1",
        column_name="Champ libre 1",
    )
    champ_libre_2 = Field(
        attribute="projet__dossier_ds__annotations_champ_libre_2",
        column_name="Champ libre 2",
    )
    champ_libre_3 = Field(
        attribute="projet__dossier_ds__annotations_champ_libre_3",
        column_name="Champ libre 3",
    )
    porteur_name = Field(
        attribute="projet__dossier_ds__porteur_fullname",
        column_name="Nom et prénom du demandeur",
    )

    class Meta:
        model = SimulationProjet
        fields = (
            "date_depot",
            "dossier_number",
            "projet_intitule",
            "demandeur_name",
            "arrondissement",
            "has_double_dotations",
            "cout_total",
            "assiette",
            "demande_montant",
            "demande_taux",
            "montant",
            "taux",
            "status",
            "date_debut",
            "date_achevement",
            "budget_vert_demandeur",
            "is_budget_vert",
            "dotation",
            "categorie",
            "completed_dossier",
            "comment_1",
            "comment_2",
            "comment_3",
            "champ_libre_1",
            "champ_libre_2",
            "champ_libre_3",
            "porteur_name",
        )

    def dehydrate_completed_dossier(self, simu_projet: SimulationProjet):
        dossier_ds = simu_projet.projet.dossier_ds
        if dossier_ds.ds_state != Dossier.STATE_EN_CONSTRUCTION:
            return "Oui"
        return "Non"

    def get_headers_to_remove(self, columns_visibility):
        if not columns_visibility:
            return self._get_default_hidden_headers()

        from gsl_simulation.table_columns import SIMULATION_TABLE_COLUMNS

        hidden_resource_fields = set()
        for css_key, visible in columns_visibility.items():
            if not visible and css_key in CSS_KEY_TO_RESOURCE_FIELDS:
                hidden_resource_fields.add(CSS_KEY_TO_RESOURCE_FIELDS[css_key])

        for col in SIMULATION_TABLE_COLUMNS:
            if (
                col.hideable
                and col.css_key not in columns_visibility
                and not col.displayed_by_default
                and col.css_key in CSS_KEY_TO_RESOURCE_FIELDS
            ):
                hidden_resource_fields.add(CSS_KEY_TO_RESOURCE_FIELDS[col.css_key])

        return self._to_hidden_headers(hidden_resource_fields)

    def _get_default_hidden_headers(self):
        from gsl_simulation.table_columns import SIMULATION_TABLE_COLUMNS

        hidden_resource_fields = set()
        for col in SIMULATION_TABLE_COLUMNS:
            if (
                col.hideable
                and not col.displayed_by_default
                and col.css_key in CSS_KEY_TO_RESOURCE_FIELDS
            ):
                hidden_resource_fields.add(CSS_KEY_TO_RESOURCE_FIELDS[col.css_key])

        return self._to_hidden_headers(hidden_resource_fields)

    def _to_hidden_headers(self, hidden_resource_fields):
        # demande_taux shares the same table column as demande_montant
        if "demande_montant" in hidden_resource_fields:
            hidden_resource_fields.add("demande_taux")

        return {
            self.fields[f].column_name
            for f in hidden_resource_fields
            if f in self.fields
        }


class DsilSimulationProjetResource(BaseSimulationProjetResource):
    def dehydrate_categorie(self, simu_projet: SimulationProjet):
        dp = simu_projet.dotation_projet
        dossier_ds = dp.projet.dossier_ds
        categorie = getattr(dossier_ds, "demande_categorie_dsil", None)
        return categorie.label if categorie else ""


class DetrSimulationProjetResource(BaseSimulationProjetResource):
    can_have_a_commission_detr_avis = Field(
        attribute="projet__dossier_ds__demande_montant_is_greater_than_min_montant_for_detr_commission",
        column_name="Montant demandé supérieur à 100 000€ ?",
        widget=OuiNonWidget(),
    )
    detr_avis_commission = Field(
        attribute="dotation_projet__detr_avis_commission",
        column_name="Avis de la commission",
        widget=OuiNonWidget(),
    )

    def dehydrate_categorie(self, simu_projet: SimulationProjet):
        dp = simu_projet.dotation_projet
        dossier_ds = dp.projet.dossier_ds
        if getattr(dossier_ds, "demande_has_categorie_detr", None) is False:
            return "Hors catégorie"
        categorie = getattr(dossier_ds, "demande_categorie_detr", None)
        return categorie.complete_label if categorie else ""

    class Meta:
        model = SimulationProjet
        fields = BaseSimulationProjetResource.Meta.fields + (
            "can_have_a_commission_detr_avis",
            "detr_avis_commission",
        )

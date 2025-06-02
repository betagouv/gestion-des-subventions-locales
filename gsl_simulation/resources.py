from import_export.resources import Field, ModelResource
from import_export.widgets import (
    BooleanWidget,
    DateTimeWidget,
    DateWidget,
)

from gsl_simulation.models import SimulationProjet


class OuiNonWidget(BooleanWidget):
    def render(self, value, obj=None, **kwargs):
        if value is None:
            return "Inconnu"
        return "Oui" if value else "Non"


class DsilSimulationProjetResource(ModelResource):
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
    porteur_name = Field(
        attribute="projet__dossier_ds__porteur_fullname",
        column_name="Nom et prénom du demandeur",
    )
    demandeur_code_insee = Field(
        attribute="projet__demandeur__address__commune__insee_code",
        column_name="Code INSEE commune du demandeur",
    )
    arrondissement = Field(
        attribute="projet__demandeur__address__commune__arrondissement__name",
        column_name="Code INSEE commune du demandeur",
    )
    has_double_dotations = Field(
        attribute="projet__has_double_dotations",
        column_name="Projet en double dotation",
        widget=OuiNonWidget(),
    )
    cout_total = Field(
        attribute="projet__dossier_ds__finance_cout_total",
        column_name="Coût total du projet",
    )
    assiette = Field(
        attribute="dotation_projet__assiette",
        column_name="Assiette subventionnable",
    )
    demande_montant = Field(
        attribute="projet__dossier_ds__demande_montant",
        column_name="Montant demandé",
    )
    demande_taux = Field(
        attribute="projet__dossier_ds__taux_demande",
        column_name="Taux demandé par rapport au coût total",
    )
    status = Field(
        attribute="get_status_display",
        column_name="Statut de la simulation",
    )
    montant = Field(
        attribute="montant",
        column_name="Montant prévsionnel accordé",
    )
    taux = Field(
        attribute="taux",
        column_name="Taux prévsionnel accordé",
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
    is_in_qpv = Field(
        attribute="projet__is_in_qpv",
        column_name="Projet situé dans un QPV",
        widget=OuiNonWidget(),
    )
    is_attached_to_a_crte = Field(
        attribute="projet__is_attached_to_a_crte",
        column_name="Projet rattaché à un CRTE",
        widget=OuiNonWidget(),
    )
    is_budget_vert = Field(
        attribute="projet__is_budget_vert",
        column_name="Projet concourant à la transition écologique",
        widget=OuiNonWidget(),
    )
    priorite = Field(
        attribute="projet__dossier_ds__demande_priorite_dsil_detr",
        column_name="Priorité du projet",
    )
    annotations = Field(
        attribute="projet__dossier_ds__annotations_champ_libre",
        column_name="Annotation de l’instructeur",
    )

    class Meta:
        model = SimulationProjet
        fields = (
            "date_depot",
            "dossier_number",
            "projet_intitule",
            "demandeur_name",
            "porteur_name",
            "demandeur_code_insee",
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
            "is_in_qpv",
            "is_attached_to_a_crte",
            "is_budget_vert",
            "demande_priorite_dsil_detr",
            "priorite",
            "annotations",
        )


class DetrSimulationProjetResource(DsilSimulationProjetResource):
    can_have_a_commission_detr_avis = Field(
        attribute="projet__dossier_ds__demande_montant_is_greater_thant_min_montant_for_detr_commission",
        column_name="Montant demandé supérieur à 100 000€ ?",
        widget=OuiNonWidget(),
    )
    detr_avis_commission = Field(
        attribute="dotation_projet__detr_avis_commission",
        column_name="Avis de la commission",
        widget=OuiNonWidget(),
    )

    class Meta:
        model = SimulationProjet
        fields = DsilSimulationProjetResource.Meta.fields + (
            "can_have_a_commission_detr_avis",
            "detr_avis_commission",
        )

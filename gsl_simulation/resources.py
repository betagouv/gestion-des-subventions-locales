from import_export.resources import Field, ModelResource
from import_export.widgets import ForeignKeyWidget

from gsl_simulation.models import SimulationProjet


class SimulationProjetResource(ModelResource):
    dossier_number = Field(
        attribute="dossier_ds",
        column_name="Numéro de dossier DS",
        widget=ForeignKeyWidget("dossier_ds", field="ds_number"),
    )
    has_double_dotations = Field(
        attribute="projet",
        column_name="Projet en double dotation",
        widget=ForeignKeyWidget("projet", field="has_double_dotations"),
    )

    montant = Field(
        attribute="montant",
        column_name="Montant retenu",
    )
    taux = Field(
        attribute="taux",
        column_name="Taux",
    )

    class Meta:
        model = SimulationProjet
        fields = (
            "dossier_number",
            "dossier_ds.projet_intitule",
            "has_double_dotations",
            "montant",
            "taux",
            "status",
        )
        # export_order = (
        #     "id",
        #     "enveloppe",
        #     "montant",
        #     "annee",
        #     "perimetre",
        #     "dotation",
        # )

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.models import Dossier, FieldMappingForComputer


class DsService:
    def __init__(self):
        self.mutator = DsMutator()

    def update_ds_is_qpv(self, dossier: Dossier, user: Collegue, value: str):
        instructeur_id = user.ds_id
        field = FieldMappingForComputer.objects.get(
            demarche=dossier.ds_demarche_id, django_field="annotations_is_qpv"
        )
        field_id = field.ds_field_id
        return self.mutator.dossier_modifier_annotation_checkbox(
            dossier.ds_id, instructeur_id, field_id, value
        )

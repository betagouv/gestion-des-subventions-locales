from gsl_demarches_simplifiees.models import Dossier, FieldMappingForComputer


class DossierConverter:
    def __init__(self, ds_dossier_data, dossier):
        self.ds_field_ids = tuple(champ["id"] for champ in ds_dossier_data["champs"])

        self.computed_mappings = FieldMappingForComputer.objects.filter(
            ds_field_id__in=self.ds_field_ids
        ).exclude(django_field="")

        self.ds_id_to_django_field = {
            mapping.ds_field_id: Dossier._meta.get_field(mapping.django_field)
            for mapping in self.computed_mappings.all()
        }

        self.dossier = dossier

# import logging

# from django.db.models.signals import post_save, pre_save
# from django.dispatch import receiver

# from gsl_core.models import Arrondissement as CoreArrondissement
# from gsl_core.models import Departement as CoreDepartement
# from gsl_demarches_simplifiees.models import Arrondissement as DsArrondissement
# from gsl_demarches_simplifiees.models import Departement as DsDepartement
# from gsl_demarches_simplifiees.models import Dossier
# from gsl_demarches_simplifiees.tasks import task_refresh_dossier_from_saved_data

# logger = logging.getLogger(__name__)


# # @receiver(pre_save, sender=DsArrondissement)
# # def associate_with_core_arrondissement(
# #     sender, instance: DsArrondissement, *args, **kwargs
# # ):
# #     if instance.core_arrondissement is not None:
# #         return
# #     for core_arrondissement in CoreArrondissement.objects.select_related(
# #         "departement"
# #     ).all():
# #         # instance label is like "43 - Haute-Loire - arrondissement de Brioude"
# #         if instance.label.startswith(
# #             core_arrondissement.departement.insee_code
# #         ) and instance.label.endswith(core_arrondissement.name):
# #             instance.core_arrondissement = core_arrondissement
# #             return
# #     logger.warning(
# #         f"Unable to match a CoreArrondissement with DN Arrondissement '{instance.label}'."
# #     )


# # @receiver(pre_save, sender=DsDepartement)
# # def associate_with_core_departement(sender, instance: DsDepartement, *args, **kwargs):
# #     if instance.core_departement is not None:
# #         return
# #     # instance label is like "43 - Haute-Loire": match on Insee code
# #     instance_insee_code = instance.label.split(" ")[0]
# #     core_departement_qs = CoreDepartement.objects.filter(insee_code=instance_insee_code)
# #     if core_departement_qs.exists():
# #         instance.core_departement = core_departement_qs.get()
# #         return
# #     logger.warning(
# #         f"Unable to match a CoreDepartement with DS departement '{instance.label}'."
# #     )


# # @receiver(post_save, sender=DsArrondissement)
# # def refresh_associated_projets(sender, instance: DsArrondissement, *args, **kwargs):
# #     if instance.core_arrondissement is None:
# #         return

# #     for dossier_number in Dossier.objects.filter(
# #         porteur_de_projet_arrondissement=instance
# #     ).values_list("ds_number", flat=True):
# #         task_refresh_dossier_from_saved_data.delay(dossier_number)

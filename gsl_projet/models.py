from django.db import models

from gsl_core.models import Adresse, Arrondissement, Collegue, Departement
from gsl_demarches_simplifiees.models import Dossier


class Demandeur(models.Model):
    siret = models.CharField("Siret")
    name = models.CharField("Nom")

    address = models.OneToOneField(Adresse, on_delete=models.CASCADE)
    arrondissement = models.ForeignKey(Arrondissement, on_delete=models.PROTECT)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Demandeur {self.name}"


class ProjetManager(models.Manager):
    def for_user(self, user: Collegue):
        return self.filter(
            dossier_ds__ds_demarche__ds_instructeurs__ds_email=user.email
        )

    def get_queryset(self):
        return super().get_queryset().select_related("dossier_ds")


class Projet(models.Model):
    # demandeur = models.ForeignKey(Demandeur, on_delete=models.PROTECT)
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)

    address = models.OneToOneField(Adresse, on_delete=models.CASCADE)
    # arrondissement = models.ForeignKey(Arrondissement, on_delete=models.PROTECT)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    objects = ProjetManager()

    def __str__(self):
        return f"Projet {self.pk} — Dossier {self.dossier_ds.ds_number}"

    @classmethod
    def get_or_create_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = cls.objects.get(dossier_ds=ds_dossier)
        except cls.DoesNotExist:
            projet_adresse = ds_dossier.projet_adresse.clone()
            projet_adresse.save()
            projet = cls(
                dossier_ds=ds_dossier,
                address=projet_adresse,
                # arrondissement=ds_dossier.porteur_de_projet_arrondissement,
                departement=ds_dossier.projet_adresse.commune.departement,
            )
            projet.save()
        return projet

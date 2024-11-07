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


class Projet(models.Model):
    demandeur = models.ForeignKey(Demandeur, on_delete=models.PROTECT)
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)

    address = models.OneToOneField(Adresse, on_delete=models.CASCADE)
    arrondissement = models.ForeignKey(Arrondissement, on_delete=models.PROTECT)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    objects = ProjetManager()

    def __str__(self):
        return f"Projet {self.pk}"

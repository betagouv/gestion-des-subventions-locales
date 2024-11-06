from django.db import models

from gsl_core.models import Adresse, Arrondissement, Departement
from gsl_demarches_simplifiees.models import Dossier


class Demandeur(models.Model):
    siret = models.CharField("Siret")
    name = models.CharField("Nom")

    address = models.OneToOneField(Adresse, on_delete=models.CASCADE)
    arrondissement = models.ForeignKey(Arrondissement, on_delete=models.PROTECT)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Demandeur {self.name}"


class Projet(models.Model):
    demandeur = models.ForeignKey(Demandeur, on_delete=models.PROTECT)
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)

    address = models.OneToOneField(Adresse, on_delete=models.CASCADE)
    arrondissement = models.ForeignKey(Arrondissement, on_delete=models.PROTECT)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Projet {self.pk}"

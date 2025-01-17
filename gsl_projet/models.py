from django.db import models

from gsl_core.models import Adresse, Arrondissement, Collegue, Departement, Perimetre
from gsl_demarches_simplifiees.models import Dossier


class Demandeur(models.Model):
    siret = models.CharField("Siret")
    name = models.CharField("Nom")

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT)
    arrondissement = models.ForeignKey(
        Arrondissement, on_delete=models.PROTECT, null=True
    )
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Demandeur {self.name}"


class ProjetManager(models.Manager):
    def for_user(self, user: Collegue):
        return self.for_perimetre(user.perimetre)

    def for_perimetre(self, perimetre: Perimetre):
        if perimetre is None:
            return self
        if perimetre.arrondissement:
            return self.filter(demandeur__arrondissement=perimetre.arrondissement)
        if perimetre.departement:
            return self.filter(demandeur__departement=perimetre.departement)
        if perimetre.region:
            return self.filter(demandeur__departement__region=perimetre.region)

    def get_queryset(self):
        return super().get_queryset().select_related("dossier_ds")


class Projet(models.Model):
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)
    demandeur = models.ForeignKey(Demandeur, on_delete=models.PROTECT, null=True)

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT, null=True)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT, null=True)

    assiette = models.DecimalField(
        "Assiette subventionnable",
        max_digits=12,
        decimal_places=2,
        null=True,
    )

    avis_commission_detr = models.BooleanField(
        "Avis commission DETR",
        help_text="Pour les projets de plus de 100 000 €",
        null=True,
    )
    free_comment = models.TextField("Commentaires libres", blank=True, default="")

    objects = ProjetManager()

    def __str__(self):
        return f"Projet {self.pk} — Dossier {self.dossier_ds.ds_number}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("projet:get-projet", kwargs={"projet_id": self.id})

    @classmethod
    def get_or_create_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = cls.objects.get(dossier_ds=ds_dossier)
        except cls.DoesNotExist:
            projet = cls(
                dossier_ds=ds_dossier,
            )
        projet.address = ds_dossier.projet_adresse
        projet.demandeur, _ = Demandeur.objects.get_or_create(
            siret=ds_dossier.ds_demandeur.siret,
            defaults={
                "name": ds_dossier.ds_demandeur.raison_sociale,
                "address": ds_dossier.ds_demandeur.address,
                "departement": ds_dossier.ds_demandeur.address.commune.departement,
            },
        )
        if projet.address is not None and projet.address.commune is not None:
            projet.departement = projet.address.commune.departement

        projet.save()
        return projet

    @property
    def assiette_or_cout_total(self):
        if self.assiette:
            return self.assiette
        return self.dossier_ds.finance_cout_total

    def get_taux_de_subvention_sollicite(self):
        if self.assiette_or_cout_total is None:
            return
        if self.assiette_or_cout_total > 0:
            return self.dossier_ds.demande_montant / self.assiette_or_cout_total

    def get_taux_subventionnable(self):
        if self.assiette is None:
            return

        if self.assiette > 0:
            return int(100 * self.assiette / self.dossier_ds.finance_cout_total)

    @property
    def categorie_doperation(self):
        if "DETR" in self.dossier_ds.demande_dispositif_sollicite:
            yield from self.dossier_ds.demande_eligibilite_detr.all()
        if "DSIL" in self.dossier_ds.demande_dispositif_sollicite:
            yield from self.dossier_ds.demande_eligibilite_dsil.all()

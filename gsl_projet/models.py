from datetime import UTC, date, datetime
from datetime import timezone as tz
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q

from gsl_core.models import Adresse, Arrondissement, Collegue, Departement, Perimetre
from gsl_demarches_simplifiees.models import Dossier

if TYPE_CHECKING:
    from gsl_programmation.models import Enveloppe


class Demandeur(models.Model):
    siret = models.CharField("Siret", unique=True)
    name = models.CharField("Nom")

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT)
    arrondissement = models.ForeignKey(
        Arrondissement, on_delete=models.PROTECT, null=True
    )
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Demandeur {self.name}"


class ProjetQuerySet(models.QuerySet):
    def for_user(self, user: Collegue):
        if user.perimetre is None:
            if user.is_staff or user.is_superuser:
                return self
            return self.none()

        return self.for_perimetre(user.perimetre)

    def for_perimetre(self, perimetre: Perimetre | None):
        if perimetre is None:
            return self
        if perimetre.arrondissement:
            return self.filter(demandeur__arrondissement=perimetre.arrondissement)
        if perimetre.departement:
            return self.filter(demandeur__departement=perimetre.departement)
        if perimetre.region:
            return self.filter(demandeur__departement__region=perimetre.region)

    def for_current_year(self):
        return self.filter(
            Q(
                dossier_ds__ds_state__in=[
                    Dossier.STATE_EN_CONSTRUCTION,
                    Dossier.STATE_EN_INSTRUCTION,
                ]
            )
            | Q(
                dossier_ds__ds_state__in=[
                    Dossier.STATE_ACCEPTE,
                    Dossier.STATE_SANS_SUITE,
                    Dossier.STATE_REFUSE,
                ],
                dossier_ds__ds_date_traitement__gte=datetime(
                    date.today().year, 1, 1, 0, 0, tzinfo=tz.utc
                ),
            )
        )

    def included_in_enveloppe(self, enveloppe: "Enveloppe"):
        projet_qs = self.for_perimetre(enveloppe.perimetre)
        projet_qs_with_the_right_type = projet_qs.filter(
            dossier_ds__demande_dispositif_sollicite=enveloppe.type,
        )
        projet_qs_submitted_before_the_end_of_the_year = (
            projet_qs_with_the_right_type.filter(
                dossier_ds__ds_date_depot__lt=datetime(
                    enveloppe.annee + 1, 1, 1, tzinfo=UTC
                ),
            )
        )
        projet_qs_not_processed_before_the_start_of_the_year = (
            projet_qs_submitted_before_the_end_of_the_year.filter(
                Q(
                    dossier_ds__ds_date_traitement__gte=datetime(
                        enveloppe.annee, 1, 1, tzinfo=UTC
                    )
                )
                | Q(
                    dossier_ds__ds_date_traitement__isnull=True,
                )
            )
        )
        return projet_qs_not_processed_before_the_start_of_the_year

    def processed_in_enveloppe(self, enveloppe: "Enveloppe"):
        projet_qs = self.for_perimetre(enveloppe.perimetre)
        projet_qs_with_the_right_type = projet_qs.filter(
            dossier_ds__demande_dispositif_sollicite=enveloppe.type,
        )
        projet_qs_with_a_processed_state = projet_qs_with_the_right_type.filter(
            dossier_ds__ds_state__in=[
                Dossier.STATE_ACCEPTE,
                Dossier.STATE_REFUSE,
                Dossier.STATE_SANS_SUITE,
            ]
        )
        projet_qs_processed_during_the_year = projet_qs_with_a_processed_state.filter(
            Q(
                dossier_ds__ds_date_traitement__gte=datetime(
                    enveloppe.annee, 1, 1, tzinfo=UTC
                )
            )
            & Q(
                dossier_ds__ds_date_traitement__lt=datetime(
                    enveloppe.annee + 1, 1, 1, tzinfo=UTC
                )
            )
        )
        return projet_qs_processed_during_the_year


class ProjetManager(models.Manager.from_queryset(ProjetQuerySet)):
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

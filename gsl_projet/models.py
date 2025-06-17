from datetime import UTC, date, datetime
from datetime import timezone as tz
from typing import TYPE_CHECKING, Iterator, Union

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.forms import ValidationError
from django.utils import timezone
from django_fsm import FSMField, transition

from gsl_core.models import Adresse, BaseModel, Collegue, Departement, Perimetre
from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import (
    DOTATION_CHOICES,
    DOTATION_DETR,
    DOTATION_DSIL,
    MIN_DEMANDE_MONTANT_FOR_AVIS_DETR,
    POSSIBLE_DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_CHOICES,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)

if TYPE_CHECKING:
    from gsl_demarches_simplifiees.models import CritereEligibiliteDsil, Dossier
    from gsl_programmation.models import Enveloppe


class CategorieDetrQueryset(models.QuerySet):
    def most_recent_for_departement(self, departement: Departement):
        annee = timezone.now().year
        while annee > 2022:
            qs = self.filter(departement=departement, annee=annee)
            if qs.exists():
                return qs

            annee = annee - 1
        return self.none()


class CategorieDetr(models.Model):
    libelle = models.CharField("Libellé")
    rang = models.IntegerField("Rang", default=0)
    annee = models.IntegerField("Année")
    departement = models.ForeignKey(
        Departement, verbose_name="Département", on_delete=models.PROTECT
    )

    objects = CategorieDetrQueryset.as_manager()

    class Meta:
        verbose_name = "Catégorie DETR"
        verbose_name_plural = "Catégories DETR"
        constraints = (
            UniqueConstraint(
                fields=("departement", "annee", "rang"),
                name="unique_by_departement_rang_annee",
            ),
        )

    def __str__(self):
        return f"Catégorie DETR {self.id} - {self.libelle}"


class Demandeur(models.Model):
    siret = models.CharField("Siret", unique=True)
    name = models.CharField("Nom")

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT)

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
            return self.filter(perimetre__arrondissement=perimetre.arrondissement)
        if perimetre.departement:
            return self.filter(perimetre__departement=perimetre.departement)
        if perimetre.region:
            return self.filter(perimetre__region=perimetre.region)

    def for_current_year(self):
        return self.not_processed_before_the_start_of_the_year(date.today().year)

    def not_processed_before_the_start_of_the_year(self, year: int):
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
                    year, 1, 1, 0, 0, tzinfo=tz.utc
                ),
            )
        )

    def included_in_enveloppe(self, enveloppe: "Enveloppe"):
        projet_qs = self.for_perimetre(enveloppe.perimetre)
        projet_qs_with_the_correct_dotation = projet_qs.filter(
            dotationprojet__dotation=enveloppe.dotation
        )
        projet_qs_submitted_before_the_end_of_the_year = (
            projet_qs_with_the_correct_dotation.filter(
                dossier_ds__ds_date_depot__lt=datetime(
                    enveloppe.annee + 1, 1, 1, tzinfo=UTC
                ),
            )
        )
        projet_qs_not_processed_before_the_start_of_the_year = projet_qs_submitted_before_the_end_of_the_year.not_processed_before_the_start_of_the_year(
            enveloppe.annee
        )
        return projet_qs_not_processed_before_the_start_of_the_year


class ProjetManager(models.Manager.from_queryset(ProjetQuerySet)):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("dossier_ds")
            .prefetch_related("dotationprojet_set")
        )


class Projet(models.Model):
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)
    demandeur = models.ForeignKey(Demandeur, on_delete=models.PROTECT, null=True)

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT, null=True)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT, null=True)
    perimetre = models.ForeignKey(Perimetre, on_delete=models.PROTECT, null=True)

    status = models.CharField(
        verbose_name="Statut",
        choices=PROJET_STATUS_CHOICES,
        default=PROJET_STATUS_PROCESSING,
    )

    is_in_qpv = models.BooleanField("Projet situé en QPV", null=False, default=False)
    is_attached_to_a_crte = models.BooleanField(
        "Projet rattaché à un CRTE",
        null=False,
        default=False,
    )
    is_budget_vert = models.BooleanField(
        "Projet concourant à la transition écologique au sens budget vert",
        null=True,
        default=False,
    )
    free_comment = models.TextField("Commentaires libres", blank=True, default="")

    objects = ProjetManager()

    def __str__(self):
        return f"Projet {self.pk} — Dossier {self.dossier_ds.ds_number}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("projet:get-projet", kwargs={"projet_id": self.id})

    @property
    def can_have_a_commission_detr_avis(self) -> bool:
        return (
            self.dotationprojet_set.filter(dotation=DOTATION_DETR).exists()
            and self.dossier_ds.demande_montant is not None
            and self.dossier_ds.demande_montant >= MIN_DEMANDE_MONTANT_FOR_AVIS_DETR
        )

    @property
    def categories_doperation(
        self,
    ) -> Iterator[Union["CategorieDetr", "CritereEligibiliteDsil"]]:
        if self.dotation_detr:
            yield from self.dotation_detr.detr_categories.all()
        if DOTATION_DSIL in self.dossier_ds.demande_dispositif_sollicite:
            yield from self.dossier_ds.demande_eligibilite_dsil.all()

    @property
    def dotations(self) -> list[POSSIBLE_DOTATIONS]:
        return [
            dotation.dotation
            for dotation in self.dotationprojet_set.all()
            if dotation.dotation in [DOTATION_DETR, DOTATION_DSIL]
        ]

    @property
    def has_double_dotations(self):
        return self.dotationprojet_set.count() > 1

    @property
    def dotation_detr(self):
        for dp in self.dotationprojet_set.all():
            if dp.dotation == DOTATION_DETR:
                return dp

    @property
    def dotation_dsil(self):
        for dp in self.dotationprojet_set.all():
            if dp.dotation == DOTATION_DSIL:
                return dp

    @property
    def to_notify(self) -> bool:
        from gsl_programmation.models import ProgrammationProjet

        return ProgrammationProjet.objects.filter(
            dotation_projet__projet=self,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            notified_at__isnull=True,
        ).exists()


class DotationProjet(models.Model):
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE)
    dotation = models.CharField("Dotation", choices=DOTATION_CHOICES)
    # TODO pr_dotation put back protected=True, once every status transition is handled ?
    status = FSMField(
        "Statut",
        choices=PROJET_STATUS_CHOICES,
        default=PROJET_STATUS_PROCESSING,
    )
    assiette = models.DecimalField(
        "Assiette subventionnable",
        max_digits=12,
        decimal_places=2,
        null=True,
    )
    detr_avis_commission = models.BooleanField(
        "Avis commission DETR",
        help_text="Pour les projets de plus de 100 000 €",
        null=True,
    )
    detr_categories = models.ManyToManyField(
        CategorieDetr, verbose_name="Catégories d’opération DETR"
    )

    class Meta:
        unique_together = ("projet", "dotation")
        verbose_name = "Dotation projet"
        verbose_name_plural = "Dotations projet"

    def __str__(self):
        return f"Projet {self.projet_id} - Dotation {self.dotation}"

    def clean(self):
        errors = {}
        if self.detr_avis_commission is not None:
            if self.dotation == DOTATION_DSIL:
                errors["detr_avis_commission"] = (
                    "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
                )

            if (
                self.dossier_ds.demande_montant is not None
                and self.dossier_ds.demande_montant < MIN_DEMANDE_MONTANT_FOR_AVIS_DETR
            ):
                errors["detr_avis_commission"] = (
                    f"L'avis de la commission DETR ne doit être renseigné que pour les projets DETR dont le montant demandé est supérieur ou égal à {MIN_DEMANDE_MONTANT_FOR_AVIS_DETR}."
                )

        if (
            self.dossier_ds.finance_cout_total
            and self.assiette
            and self.dossier_ds.finance_cout_total < self.assiette
        ):
            errors["assiette"] = (
                "L'assiette ne doit pas être supérieure au coût total du projet."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def dossier_ds(self):
        return self.projet.dossier_ds

    @property
    def assiette_or_cout_total(self):
        if self.assiette:
            return self.assiette
        return self.dossier_ds.finance_cout_total

    @property
    def taux_de_subvention_sollicite(self) -> float | None:
        if (
            self.assiette_or_cout_total is not None
            and self.dossier_ds.demande_montant is not None
            and self.assiette_or_cout_total > 0
        ):
            return self.dossier_ds.demande_montant * 100 / self.assiette_or_cout_total
        return None

    @property
    def montant_retenu(self) -> float | None:
        if hasattr(self, "programmation_projet"):
            return self.programmation_projet.montant
        return None

    @property
    def taux_retenu(self) -> float | None:
        if hasattr(self, "programmation_projet"):
            return self.programmation_projet.taux
        return None

    @transition(field=status, source="*", target=PROJET_STATUS_ACCEPTED)
    def accept(self, montant: float, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_programmation.services.enveloppe_service import EnveloppeService
        from gsl_simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_ACCEPTED,
            montant=montant,
        )

        parent_enveloppe = EnveloppeService.get_parent_enveloppe(enveloppe)

        ProgrammationProjet.objects.update_or_create(
            dotation_projet=self,
            enveloppe=parent_enveloppe,
            defaults={
                "montant": montant,
                "status": ProgrammationProjet.STATUS_ACCEPTED,
            },
        )

    @transition(field=status, source="*", target=PROJET_STATUS_REFUSED)
    def refuse(self, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_programmation.services.enveloppe_service import EnveloppeService
        from gsl_simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_REFUSED,
            montant=0,
        )

        parent_enveloppe = EnveloppeService.get_parent_enveloppe(enveloppe)

        ProgrammationProjet.objects.update_or_create(
            dotation_projet=self,
            enveloppe=parent_enveloppe,
            defaults={
                "montant": 0,
                "status": ProgrammationProjet.STATUS_REFUSED,
            },
        )

    @transition(field=status, source="*", target=PROJET_STATUS_DISMISSED)
    def dismiss(self):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_DISMISSED, montant=0
        )

        ProgrammationProjet.objects.filter(dotation_projet=self).delete()

    @transition(
        field=status,
        source=[PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED],
        target=PROJET_STATUS_PROCESSING,
    )
    def set_back_status_to_processing(self):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_PROCESSING,
        )

        ProgrammationProjet.objects.filter(dotation_projet=self).delete()


class ProjetNote(BaseModel):
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=100)
    content = models.TextField()
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)

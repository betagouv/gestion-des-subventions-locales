from datetime import UTC, date, datetime
from datetime import timezone as tz
from functools import cached_property
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q
from django_fsm import FSMField, transition

from gsl_core.models import Adresse, Collegue, Departement, Perimetre
from gsl_demarches_simplifiees.models import Dossier

if TYPE_CHECKING:
    from gsl_programmation.models import Enveloppe


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
        projet_qs_not_processed_before_the_start_of_the_year = projet_qs_submitted_before_the_end_of_the_year.not_processed_before_the_start_of_the_year(
            enveloppe.annee
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
    perimetre = models.ForeignKey(Perimetre, on_delete=models.PROTECT, null=True)

    STATUS_ACCEPTED = "accepted"
    STATUS_REFUSED = "refused"
    STATUS_PROCESSING = "processing"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = (
        (STATUS_ACCEPTED, "✅ Accepté"),
        (STATUS_REFUSED, "❌ Refusé"),
        (STATUS_PROCESSING, "🔄 En traitement"),
        (STATUS_DISMISSED, "⛔️ Classé sans suite"),
    )
    # TODO put back protected=True, once every status transition is handled
    status = FSMField("Statut", choices=STATUS_CHOICES, default=STATUS_PROCESSING)

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

    @property
    def assiette_or_cout_total(self):
        if self.assiette:
            return self.assiette
        return self.dossier_ds.finance_cout_total

    @cached_property
    def accepted_programmation_projet(self):
        if (
            hasattr(self, "accepted_programmation_projets")
            and len(self.accepted_programmation_projets) > 0
        ):
            return self.accepted_programmation_projets[0]

    @property
    def montant_retenu(self) -> float | None:
        if self.accepted_programmation_projet:
            return self.accepted_programmation_projet.montant
        return None

    @property
    def taux_retenu(self) -> float | None:
        if self.accepted_programmation_projet:
            return self.accepted_programmation_projet.taux
        return None

    @property
    def is_asking_for_detr(self) -> bool:
        return "DETR" in self.dossier_ds.demande_dispositif_sollicite

    @property
    def categorie_doperation(self):
        if "DETR" in self.dossier_ds.demande_dispositif_sollicite:
            yield from self.dossier_ds.demande_eligibilite_detr.all()
        if "DSIL" in self.dossier_ds.demande_dispositif_sollicite:
            yield from self.dossier_ds.demande_eligibilite_dsil.all()

    def get_taux_de_subvention_sollicite(self):
        if (
            self.assiette_or_cout_total is None
            or self.dossier_ds.demande_montant is None
        ):
            return
        if self.assiette_or_cout_total > 0:
            return self.dossier_ds.demande_montant * 100 / self.assiette_or_cout_total

    def get_taux_subventionnable(self):
        if self.assiette is None:
            return

        if self.assiette > 0:
            return int(100 * self.assiette / self.dossier_ds.finance_cout_total)

    @transition(field=status, source="*", target=STATUS_ACCEPTED)
    def accept(self, montant: float, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_programmation.services.enveloppe_service import EnveloppeService
        from gsl_projet.services import ProjetService
        from gsl_simulation.models import SimulationProjet

        taux = ProjetService.compute_taux_from_montant(self, montant)

        SimulationProjet.objects.filter(projet=self).update(
            status=SimulationProjet.STATUS_ACCEPTED,
            montant=montant,
            taux=taux,
        )

        parent_enveloppe = EnveloppeService.get_parent_enveloppe(enveloppe)

        ProgrammationProjet.objects.update_or_create(
            projet=self,
            enveloppe=parent_enveloppe,
            defaults={
                "montant": montant,
                "taux": taux,
                "status": ProgrammationProjet.STATUS_ACCEPTED,
            },
        )

    @transition(field=status, source="*", target=STATUS_REFUSED)
    def refuse(self, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_programmation.services.enveloppe_service import EnveloppeService
        from gsl_simulation.models import SimulationProjet

        SimulationProjet.objects.filter(projet=self).update(
            status=SimulationProjet.STATUS_REFUSED,
            montant=0,
            taux=0,
        )

        parent_enveloppe = EnveloppeService.get_parent_enveloppe(enveloppe)

        ProgrammationProjet.objects.update_or_create(
            projet=self,
            enveloppe=parent_enveloppe,
            defaults={
                "montant": 0,
                "taux": 0,
                "status": ProgrammationProjet.STATUS_REFUSED,
            },
        )

    @transition(
        field=status,
        source=[STATUS_ACCEPTED, STATUS_REFUSED, STATUS_DISMISSED],
        target=STATUS_PROCESSING,
    )
    def set_back_status_to_processing(self):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        SimulationProjet.objects.filter(projet=self).update(
            status=SimulationProjet.STATUS_PROCESSING,
        )

        ProgrammationProjet.objects.filter(projet=self).delete()

    @transition(field=status, source="*", target=STATUS_DISMISSED)
    def dismiss(self):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        SimulationProjet.objects.filter(projet=self).update(
            status=SimulationProjet.STATUS_DISMISSED, montant=0, taux=0
        )

        ProgrammationProjet.objects.filter(projet=self).delete()

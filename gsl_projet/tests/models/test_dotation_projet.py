from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.forms import ValidationError

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, DOTATIONS
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory


@pytest.mark.parametrize(("dotation"), DOTATIONS)
@pytest.mark.django_db
def test_dotation_projet_unicity(dotation):
    projet = ProjetFactory()
    DotationProjet(projet=projet, dotation=dotation).save()
    with pytest.raises(IntegrityError):
        DotationProjet(projet=projet, dotation=dotation).save()


@pytest.mark.django_db
def test_dsil_dotation_projet_must_have_a_detr_avis_commission_null():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL, detr_avis_commission=True
    )
    with pytest.raises(ValidationError) as exc_info:
        dotation_projet.full_clean()

    assert exc_info.value.message_dict["detr_avis_commission"][0] == (
        "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
    )


@pytest.mark.django_db
def test_assiette_or_cout_total():
    dotation_projet = DotationProjetFactory(
        assiette=1_000, projet__dossier_ds__finance_cout_total=2_000
    )
    assert dotation_projet.assiette_or_cout_total == 1_000

    dotation_projet = DotationProjetFactory(
        assiette=None, projet__dossier_ds__finance_cout_total=2_000
    )
    assert dotation_projet.assiette_or_cout_total == 2_000


# Accept


@pytest.mark.django_db
def test_accept_projet_without_simulation_projet():
    dotation_projet = DotationProjetFactory(assiette=10_000, dotation=DOTATION_DETR)
    assert dotation_projet.projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2025)

    dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    dotation_projet.projet.save()
    dotation_projet.projet.refresh_from_db()

    assert dotation_projet.status == DotationProjet.STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    assert simulation_projets.count() == 0

    # TODO pr_dotation replace projet by dotation_projet
    programmation_projets = ProgrammationProjet.objects.filter(
        projet=dotation_projet.projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet():
    dotation_projet = DotationProjetFactory(assiette=10_000, dotation=DOTATION_DETR)
    assert dotation_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROVISOIRE,
        montant=1_000,
    )
    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_REFUSED,
        montant=2_000,
    )
    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=3_000,
    )
    assert SimulationProjet.objects.filter(dotation_projet=dotation_projet).count() == 3

    enveloppe = DetrEnveloppeFactory(annee=2025)

    dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == DotationProjet.STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 50

    # TODO pr_dotation replace projet by dotation_projet
    programmation_projets = ProgrammationProjet.objects.filter(
        projet=dotation_projet.projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet_update_programmation_projet():
    dotation_projet = DotationProjetFactory(
        assiette=9_000, status=DotationProjet.STATUS_REFUSED, dotation=DOTATION_DETR
    )

    enveloppe = DetrEnveloppeFactory(annee=2025)
    ProgrammationProjetFactory(
        projet=dotation_projet.projet,
        enveloppe=enveloppe,
        montant=0,
        status=ProgrammationProjet.STATUS_REFUSED,
    )

    dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()
    assert dotation_projet.status == DotationProjet.STATUS_ACCEPTED

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=dotation_projet.projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == Decimal("55.56")
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet_select_parent_enveloppe():
    dotation_projet = DotationProjetFactory(
        assiette=9_000,
        status=DotationProjet.STATUS_PROCESSING,
        dotation=DOTATION_DSIL,
    )
    parent_enveloppe = DsilEnveloppeFactory()
    child_enveloppe = DsilEnveloppeFactory(deleguee_by=parent_enveloppe)
    dotation_projet.accept(montant=5_000, enveloppe=child_enveloppe)

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=dotation_projet.projet
    )

    assert programmation_projets.count() == 1
    assert programmation_projets.first().enveloppe == parent_enveloppe

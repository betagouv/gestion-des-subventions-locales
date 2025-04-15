import logging
from datetime import date
from decimal import Decimal

import pytest

from gsl_core.tests.factories import PerimetreDepartementalFactory, PerimetreFactory
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_programmation.services.programmation_projet_service import (
    ProgrammationProjetService,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.tests.factories import DotationProjetFactory


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def detr_enveloppe(perimetre):
    return DetrEnveloppeFactory(annee=date.today().year, perimetre=perimetre)


# STATUS ACCEPTED
@pytest.fixture
def accepted_dotation_projet(perimetre):
    return DotationProjetFactory(
        status=Projet.STATUS_ACCEPTED,
        assiette=3_000,
        dotation=DOTATION_DETR,
        projet__perimetre=perimetre,
    )


@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_no_existing_one_and_complete_annotations(
    accepted_dotation_projet, detr_enveloppe
):
    accepted_dotation_projet.projet.dossier_ds.annotations_montant_accorde = 1_000
    accepted_dotation_projet.projet.dossier_ds.annotations_taux = 0.33
    accepted_dotation_projet.projet.dossier_ds.annotations_assiette = 3_000
    ProgrammationProjetFactory.create_batch(10)
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=accepted_dotation_projet
        ).count()
        == 0
    )
    assert ProgrammationProjet.objects.count() == 10

    ProgrammationProjetService.create_or_update_from_dotation_projet(
        accepted_dotation_projet
    )

    programmation_projet = ProgrammationProjet.objects.get(
        dotation_projet=accepted_dotation_projet
    )
    assert programmation_projet.dotation_projet == accepted_dotation_projet
    assert programmation_projet.montant == 1_000
    assert programmation_projet.taux == Decimal("0.33")
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.enveloppe == detr_enveloppe
    assert ProgrammationProjet.objects.count() == 11


@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_an_existing_one_and_complete_annotations(
    accepted_dotation_projet, detr_enveloppe
):
    accepted_dotation_projet.dossier_ds.annotations_montant_accorde = 1_000
    accepted_dotation_projet.dossier_ds.annotations_taux = 0.25
    accepted_dotation_projet.dossier_ds.annotations_assiette = 4_000

    ProgrammationProjetFactory(
        dotation_projet=accepted_dotation_projet,
        montant=0,
        taux=0,
        status=ProgrammationProjet.STATUS_REFUSED,
        enveloppe=detr_enveloppe,
    )

    ProgrammationProjetService.create_or_update_from_dotation_projet(
        accepted_dotation_projet
    )

    programmation_projet = ProgrammationProjet.objects.get(
        dotation_projet=accepted_dotation_projet
    )
    assert programmation_projet.dotation_projet == accepted_dotation_projet
    assert programmation_projet.montant == 1_000
    assert programmation_projet.taux == 0.25
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.enveloppe == detr_enveloppe


@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_an_existing_one_with_only_dotation_in_annotations(
    perimetre, accepted_dotation_projet, detr_enveloppe, caplog
):
    PerimetreFactory(
        region=perimetre.departement.region,
        departement=None,
        arrondissement=None,
    )
    accepted_dotation_projet.dotation = DOTATION_DSIL
    ProgrammationProjetFactory(
        dotation_projet=accepted_dotation_projet, enveloppe=detr_enveloppe
    )

    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=accepted_dotation_projet
        ).count()
        == 1
    )

    with caplog.at_level(logging.ERROR):
        programmation_projet = (
            ProgrammationProjetService.create_or_update_from_dotation_projet(
                accepted_dotation_projet
            )
        )

    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=accepted_dotation_projet
        ).count()
        == 1
    )
    assert programmation_projet is None
    assert "missing field annotations_montant_accorde" in caplog.text


@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_an_existing_one_and_without_annotations(
    accepted_dotation_projet, detr_enveloppe
):
    ProgrammationProjetFactory(
        dotation_projet=accepted_dotation_projet, enveloppe=detr_enveloppe
    )

    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=accepted_dotation_projet
        ).count()
        == 1
    )

    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(
            accepted_dotation_projet
        )
    )
    assert programmation_projet is None
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=accepted_dotation_projet
        ).count()
        == 1
    )


# STATUS REFUSED


@pytest.fixture
def refused_dotation_projet(perimetre):
    return DotationProjetFactory(
        status=Projet.STATUS_REFUSED,
        dotation=DOTATION_DETR,
        projet__dossier_ds__annotations_assiette=3_000,
        projet__perimetre=perimetre,
    )


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_no_existing_one_and_complete_annotations(
    refused_dotation_projet, detr_enveloppe
):
    refused_dotation_projet.dossier_ds.annotations_montant_accorde = 0
    refused_dotation_projet.dossier_ds.annotations_taux = 0
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 0
    )

    ProgrammationProjetService.create_or_update_from_dotation_projet(
        refused_dotation_projet
    )

    programmation_projet = ProgrammationProjet.objects.get(
        dotation_projet=refused_dotation_projet
    )
    assert programmation_projet.dotation_projet == refused_dotation_projet
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.enveloppe == detr_enveloppe


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_an_existing_one_and_complete_annotations(
    refused_dotation_projet, detr_enveloppe
):
    refused_dotation_projet.dossier_ds.annotations_montant_accorde = 0
    refused_dotation_projet.dossier_ds.annotations_taux = 0

    ProgrammationProjetFactory(
        dotation_projet=refused_dotation_projet,
        montant=10,
        taux=2,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=detr_enveloppe,
    )

    ProgrammationProjetService.create_or_update_from_dotation_projet(
        refused_dotation_projet
    )

    programmation_projet = ProgrammationProjet.objects.get(
        dotation_projet=refused_dotation_projet
    )
    assert programmation_projet.dotation_projet == refused_dotation_projet
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.enveloppe == detr_enveloppe


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_existing_one_with_only_dotation_in_annotations(
    perimetre, refused_dotation_projet, detr_enveloppe
):
    refused_dotation_projet.dotation = DOTATION_DSIL
    ProgrammationProjetFactory(
        dotation_projet=refused_dotation_projet, enveloppe=detr_enveloppe
    )
    dsil_enveloppe = DsilEnveloppeFactory(
        perimetre__region=perimetre.departement.region,
        annee=date.today().year,
    )

    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 1
    )

    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(
            refused_dotation_projet
        )
    )

    programmation_projet = ProgrammationProjet.objects.get(
        dotation_projet=refused_dotation_projet
    )
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 1
    )
    assert programmation_projet.enveloppe == dsil_enveloppe
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_no_existing_one_with_only_dotation_in_annotations(
    refused_dotation_projet, detr_enveloppe
):
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 0
    )

    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(
            refused_dotation_projet
        )
    )

    programmation_projet = ProgrammationProjet.objects.get(
        dotation_projet=refused_dotation_projet
    )
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 1
    )
    assert programmation_projet.enveloppe == detr_enveloppe
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_existing_one_and_without_annotations(
    refused_dotation_projet, detr_enveloppe
):
    ProgrammationProjetFactory(
        dotation_projet=refused_dotation_projet, enveloppe=detr_enveloppe
    )

    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 1
    )

    ProgrammationProjetService.create_or_update_from_dotation_projet(
        refused_dotation_projet
    )

    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_no_existing_one_and_without_annotations(
    refused_dotation_projet, detr_enveloppe
):
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 0
    )
    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(
            refused_dotation_projet
        )
    )
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=refused_dotation_projet
        ).count()
        == 1
    )
    assert programmation_projet.dotation_projet == refused_dotation_projet
    assert programmation_projet.enveloppe == detr_enveloppe
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


# OTHER STATUS
@pytest.mark.parametrize(
    "other_status", (DotationProjet.STATUS_DISMISSED, DotationProjet.STATUS_PROCESSING)
)
@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_other_status_without_existing_one(
    other_status,
):
    dp = DotationProjetFactory(status=other_status)
    assert ProgrammationProjet.objects.count() == 0

    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(dp)
    )

    assert programmation_projet is None
    assert ProgrammationProjet.objects.count() == 0


@pytest.mark.parametrize(
    "other_status", (DotationProjet.STATUS_DISMISSED, DotationProjet.STATUS_PROCESSING)
)
@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_other_status_with_existing_one(
    perimetre, detr_enveloppe, other_status
):
    dp = DotationProjetFactory(status=other_status, projet__perimetre=perimetre)
    ProgrammationProjetFactory(dotation_projet=dp, enveloppe=detr_enveloppe)

    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(dp)
    )

    assert programmation_projet is None
    assert ProgrammationProjet.objects.count() == 0


@pytest.mark.django_db
def test_create_or_update_from_dotation_projet_with_no_corresponding_enveloppe_creating_one(
    perimetre,
):
    assert Enveloppe.objects.count() == 0
    dp = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=DotationProjet.STATUS_REFUSED,
        projet__perimetre=perimetre,
        projet__dossier_ds__ds_date_traitement=date(2021, 1, 1),
    )

    programmation_projet = (
        ProgrammationProjetService.create_or_update_from_dotation_projet(dp)
    )

    assert programmation_projet is not None
    assert ProgrammationProjet.objects.count() == 1
    assert Enveloppe.objects.count() == 1

    enveloppe = Enveloppe.objects.first()
    assert enveloppe.perimetre == perimetre
    assert enveloppe.annee == 2021
    assert enveloppe.dotation == DOTATION_DETR
    assert enveloppe.montant == 0

import logging
from datetime import date
from decimal import Decimal

import pytest

from gsl_core.tests.factories import PerimetreDepartementalFactory, PerimetreFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.services.programmation_projet_service import (
    ProgrammationProjetService,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.models import Projet
from gsl_projet.tests.factories import ProjetFactory


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def detr_enveloppe(perimetre):
    return DetrEnveloppeFactory(annee=date.today().year, perimetre=perimetre)


# STATUS ACCEPTED
@pytest.fixture
def accepted_projet(perimetre):
    return ProjetFactory(
        status=Projet.STATUS_ACCEPTED,
        assiette=3_000,
        perimetre=perimetre,
    )


@pytest.mark.django_db
def test_create_or_update_from_projet_with_no_existing_one_and_complete_annotations(
    accepted_projet, detr_enveloppe
):
    accepted_projet.dossier_ds.annotations_montant_accorde = 1_000
    accepted_projet.dossier_ds.annotations_taux = 0.33
    accepted_projet.dossier_ds.annotations_dotation = "DETR"
    accepted_projet.dossier_ds.annotations_assiette = 3_000
    ProgrammationProjetFactory.create_batch(10)
    assert ProgrammationProjet.objects.filter(projet=accepted_projet).count() == 0
    assert ProgrammationProjet.objects.count() == 10

    ProgrammationProjetService.create_or_update_from_projet(accepted_projet)

    programmation_projet = ProgrammationProjet.objects.get(projet=accepted_projet)
    assert programmation_projet.projet == accepted_projet
    assert programmation_projet.montant == 1_000
    assert programmation_projet.taux == Decimal("0.33")
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.enveloppe == detr_enveloppe
    assert ProgrammationProjet.objects.count() == 11


@pytest.mark.django_db
def test_create_or_update_from_projet_with_an_existing_one_and_complete_annotations(
    accepted_projet, detr_enveloppe
):
    accepted_projet.dossier_ds.annotations_dotation = "DETR"
    accepted_projet.dossier_ds.annotations_montant_accorde = 1_000
    accepted_projet.dossier_ds.annotations_taux = 0.25
    accepted_projet.dossier_ds.annotations_assiette = 4_000

    ProgrammationProjetFactory(
        projet=accepted_projet,
        montant=0,
        taux=0,
        status=ProgrammationProjet.STATUS_REFUSED,
        enveloppe=detr_enveloppe,
    )

    ProgrammationProjetService.create_or_update_from_projet(accepted_projet)

    programmation_projet = ProgrammationProjet.objects.get(projet=accepted_projet)
    assert programmation_projet.projet == accepted_projet
    assert programmation_projet.montant == 1_000
    assert programmation_projet.taux == 0.25
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.enveloppe == detr_enveloppe


@pytest.mark.django_db
def test_create_or_update_from_projet_with_an_existing_one_with_only_dotation_in_annotations(
    perimetre, accepted_projet, detr_enveloppe, caplog
):
    PerimetreFactory(
        region=perimetre.departement.region,
        departement=None,
        arrondissement=None,
    )
    accepted_projet.dossier_ds.annotations_dotation = "DSIL"
    ProgrammationProjetFactory(projet=accepted_projet, enveloppe=detr_enveloppe)

    assert ProgrammationProjet.objects.filter(projet=accepted_projet).count() == 1

    with caplog.at_level(logging.ERROR):
        programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
            accepted_projet
        )

    assert ProgrammationProjet.objects.filter(projet=accepted_projet).count() == 1
    assert programmation_projet is None
    assert "missing field annotations_montant_accorde" in caplog.text


@pytest.mark.django_db
def test_create_or_update_from_projet_with_an_existing_one_and_without_annotations(
    accepted_projet, detr_enveloppe
):
    ProgrammationProjetFactory(projet=accepted_projet, enveloppe=detr_enveloppe)

    assert ProgrammationProjet.objects.filter(projet=accepted_projet).count() == 1

    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        accepted_projet
    )
    assert programmation_projet is None
    assert ProgrammationProjet.objects.filter(projet=accepted_projet).count() == 1


# STATUS REFUSED


@pytest.fixture
def refused_projet(perimetre):
    return ProjetFactory(
        status=Projet.STATUS_REFUSED,
        dossier_ds__annotations_assiette=3_000,
        perimetre=perimetre,
    )


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_no_existing_one_and_complete_annotations(
    refused_projet, detr_enveloppe
):
    refused_projet.dossier_ds.annotations_montant_accorde = 0
    refused_projet.dossier_ds.annotations_taux = 0
    refused_projet.dossier_ds.annotations_dotation = "['DETR']"
    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 0

    ProgrammationProjetService.create_or_update_from_projet(refused_projet)

    programmation_projet = ProgrammationProjet.objects.get(projet=refused_projet)
    assert programmation_projet.projet == refused_projet
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.enveloppe == detr_enveloppe


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_an_existing_one_and_complete_annotations(
    refused_projet, detr_enveloppe
):
    refused_projet.dossier_ds.annotations_dotation = "DETR"
    refused_projet.dossier_ds.annotations_montant_accorde = 0
    refused_projet.dossier_ds.annotations_taux = 0

    ProgrammationProjetFactory(
        projet=refused_projet,
        montant=10,
        taux=2,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=detr_enveloppe,
    )

    ProgrammationProjetService.create_or_update_from_projet(refused_projet)

    programmation_projet = ProgrammationProjet.objects.get(projet=refused_projet)
    assert programmation_projet.projet == refused_projet
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.enveloppe == detr_enveloppe


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_existing_one_with_only_dotation_in_annotations(
    perimetre, refused_projet, detr_enveloppe
):
    refused_projet.dossier_ds.annotations_dotation = "DSIL"
    ProgrammationProjetFactory(projet=refused_projet, enveloppe=detr_enveloppe)
    dsil_enveloppe = DsilEnveloppeFactory(
        perimetre__region=perimetre.departement.region,
        annee=date.today().year,
    )

    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 1

    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        refused_projet
    )

    programmation_projet = ProgrammationProjet.objects.get(projet=refused_projet)
    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 1
    assert programmation_projet.enveloppe == dsil_enveloppe
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_no_existing_one_with_only_dotation_in_annotations(
    refused_projet, detr_enveloppe
):
    refused_projet.dossier_ds.annotations_dotation = "DETR"

    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 0

    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        refused_projet
    )

    programmation_projet = ProgrammationProjet.objects.get(projet=refused_projet)
    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 1
    assert programmation_projet.enveloppe == detr_enveloppe
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_existing_one_and_without_annotations(
    refused_projet, detr_enveloppe
):
    ProgrammationProjetFactory(projet=refused_projet, enveloppe=detr_enveloppe)

    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 1

    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        refused_projet
    )
    assert programmation_projet is None
    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 1


@pytest.mark.django_db
def test_create_or_update_from_refused_projet_with_no_existing_one_and_without_annotations(
    refused_projet, detr_enveloppe
):
    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        refused_projet
    )
    assert programmation_projet is None
    assert ProgrammationProjet.objects.filter(projet=refused_projet).count() == 0


# OTHER STATUS
@pytest.mark.parametrize(
    "other_status", (Projet.STATUS_DISMISSED, Projet.STATUS_PROCESSING)
)
@pytest.mark.django_db
def test_create_or_update_from_projet_with_other_status_without_existing_one(
    other_status,
):
    projet = ProjetFactory(status=other_status)
    assert ProgrammationProjet.objects.count() == 0

    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        projet
    )

    assert programmation_projet is None
    assert ProgrammationProjet.objects.count() == 0


@pytest.mark.parametrize(
    "other_status", (Projet.STATUS_DISMISSED, Projet.STATUS_PROCESSING)
)
@pytest.mark.django_db
def test_create_or_update_from_projet_with_other_status_with_existing_one(
    perimetre, detr_enveloppe, other_status
):
    projet = ProjetFactory(status=other_status, perimetre=perimetre)
    ProgrammationProjetFactory(projet=projet, enveloppe=detr_enveloppe)

    programmation_projet = ProgrammationProjetService.create_or_update_from_projet(
        projet
    )

    assert programmation_projet is None
    assert ProgrammationProjet.objects.count() == 0


@pytest.mark.parametrize(
    "dotation_annotation, dotation_expected",
    [
        ("DETR", "DETR"),
        ("['DETR']", "DETR"),
        ("['DSIL']", "DSIL"),
        ("DSIL", "DSIL"),
        ("DETR et DSIL", "Error"),
        ("Fond vert", "Error"),
        (None, "Error"),
    ],
)
@pytest.mark.django_db
def test_compute_from_annotation(dotation_annotation, dotation_expected):
    projet = ProjetFactory()
    projet.dossier_ds.annotations_dotation = dotation_annotation

    if dotation_expected == "Error":
        with pytest.raises(ValueError):
            ProgrammationProjetService.compute_from_annotation(projet)
    else:
        assert (
            ProgrammationProjetService.compute_from_annotation(projet)
            == dotation_expected
        )

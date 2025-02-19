import pytest

from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.services.programmation_projet_service import (
    ProgrammationProjetService,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DemandeurFactory, ProjetFactory


@pytest.fixture
def enveloppe():
    return DetrEnveloppeFactory()


@pytest.fixture
def demandeur(enveloppe):
    return DemandeurFactory(departement=enveloppe.perimetre.departement)


@pytest.fixture
def accepted_projet(demandeur):
    return ProjetFactory(
        status=Projet.STATUS_ACCEPTED,
        dossier_ds__annotations_montant_accorde=1_000,
        dossier_ds__annotations_taux=0.33,
        dossier_ds__annotations_dotation="DETR",
        assiette=3_000,
        demandeur=demandeur,
    )


@pytest.mark.django_db
def test_create_or_update_from_projet_with_no_existing_one_and_complete_annotations(
    accepted_projet, enveloppe
):
    ProgrammationProjetService.create_or_update_from_projet(accepted_projet)

    programmation_projet = ProgrammationProjet.objects.get(projet=accepted_projet)
    assert programmation_projet.projet == accepted_projet
    assert programmation_projet.montant == 1_000
    assert programmation_projet.taux == 0.33
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.enveloppe == enveloppe


@pytest.mark.django_db
def test_create_or_update_from_projet_with_no_existing_one_and_uncomplete_annotations(
    accepted_projet, enveloppe
):
    # ProgrammationProjetService.create_or_update_from_projet(
    #     accepted_projet
    # )

    # programmation_projet = ProgrammationProjet.objects.get(projet=accepted_projet)
    # assert programmation_projet.projet == accepted_projet
    # assert programmation_projet.montant == 1_000
    # assert programmation_projet.taux == 0.33
    # assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    # assert programmation_projet.enveloppe == enveloppe
    pass


@pytest.mark.django_db
def test_create_or_update_from_projet_with_no_existing_one_and_without_annotations(
    accepted_projet, enveloppe
):
    # ProgrammationProjetService.create_or_update_from_projet(
    #     accepted_projet
    # )

    # programmation_projet = ProgrammationProjet.objects.get(projet=accepted_projet)
    # assert programmation_projet.projet == accepted_projet
    # assert programmation_projet.montant == 1_000
    # assert programmation_projet.taux == 0.33
    # assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    # assert programmation_projet.enveloppe == enveloppe
    pass


@pytest.mark.django_db
def test_create_or_update_from_projet_with_an_existing_one(accepted_projet, enveloppe):
    ProgrammationProjetFactory(
        projet=accepted_projet,
        montant=0,
        taux=0,
        status=ProgrammationProjet.STATUS_REFUSED,
        enveloppe=enveloppe,
    )

    ProgrammationProjetService.create_or_update_from_projet(accepted_projet)

    programmation_projet = ProgrammationProjet.objects.get(projet=accepted_projet)
    assert programmation_projet.projet == accepted_projet
    assert programmation_projet.montant == 1_000
    assert programmation_projet.taux == 0.33
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.enveloppe == enveloppe


@pytest.fixture
def processing_projet(enveloppe, demandeur):
    return ProjetFactory(
        status=Projet.STATUS_PROCESSING,
        dossier_ds__annotations_montant_accorde=1_000,
        assiette=3_000,
        demandeur=demandeur,
        dossier_ds__demande_dispositif_sollicite="['DETR']",
    )


@pytest.mark.django_db
def test_create_or_update_from_projet_not_accepted_or_validated(
    processing_projet,
):
    ProgrammationProjetService.create_or_update_from_projet(processing_projet)
    with pytest.raises(ProgrammationProjet.DoesNotExist):
        ProgrammationProjet.objects.get(projet_id=processing_projet.id)


@pytest.mark.django_db
def test_create_or_update_from_projet_not_accepted_or_validated_with_existing_programmation_projet(
    processing_projet, enveloppe
):
    ProgrammationProjetFactory(
        projet=processing_projet,
        enveloppe=enveloppe,
    )
    assert ProgrammationProjet.objects.filter(projet_id=processing_projet.id).exist()

    ProgrammationProjetService.create_or_update_from_projet(processing_projet)

    with pytest.raises(ProgrammationProjet.DoesNotExist):
        ProgrammationProjet.objects.get(projet_id=processing_projet.id)

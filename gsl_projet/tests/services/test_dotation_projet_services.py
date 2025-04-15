import pytest

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "dotation_value, dotation_projet_count",
    (
        ("DETR", 1),
        ("['DETR']", 1),
        ("DSIL", 1),
        ("['DSIL']", 1),
        ("[DETR, DSIL]", 2),
        ("DETR et DSIL", 2),
        ("['DETR', 'DSIL', 'DETR et DSIL']", 2),
    ),
)
def test_create_or_update_dotation_projet_from_projet(
    field, dotation_value, dotation_projet_count
):
    projet = ProjetFactory(
        avis_commission_detr=True,
        dossier_ds__ds_state=Dossier.STATE_ACCEPTE,
        assiette=1_000,
    )
    setattr(projet.dossier_ds, field, dotation_value)

    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    assert DotationProjet.objects.count() == dotation_projet_count

    for dotation_projet in DotationProjet.objects.all():
        assert dotation_projet.projet == projet
        assert dotation_projet.status == DotationProjet.STATUS_ACCEPTED
        assert dotation_projet.assiette == 1_000
        if dotation_projet.dotation == DOTATION_DSIL:
            assert dotation_projet.detr_avis_commission is None
        else:
            assert dotation_projet.detr_avis_commission is True


@pytest.mark.django_db
def test_create_or_update_dotation_projet_from_projet_do_not_remove_dotation_projet_not_in_dossier():
    projet = ProjetFactory(dossier_ds__annotations_dotation="DETR")
    projet_dotation_dsil = DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)
    projet_dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert projet_dotation_projets.count() == 1

    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    projet_dotation_dsil.refresh_from_db()  # always exists

    projet_dotation_projets = DotationProjet.objects.filter(projet_id=projet.id)
    assert projet_dotation_projets.count() == 2

    dotation_projet = projet_dotation_projets[0]
    assert dotation_projet.dotation == DOTATION_DSIL

    dotation_projet = projet_dotation_projets[1]
    assert dotation_projet.dotation == DOTATION_DETR


@pytest.mark.django_db
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DETR, DOTATION_DSIL),
)
def test_create_or_update_dotation_projet(dotation):
    projet = ProjetFactory(
        avis_commission_detr=False,
        dossier_ds__ds_state=Dossier.STATE_SANS_SUITE,
        assiette=2_000,
    )

    DotationProjetService.create_or_update_dotation_projet(projet, dotation)

    assert DotationProjet.objects.count() == 1

    dotation_projet = DotationProjet.objects.first()
    assert dotation_projet.projet == projet
    assert dotation_projet.dotation == dotation
    assert dotation_projet.status == DotationProjet.STATUS_DISMISSED
    assert dotation_projet.assiette == 2_000
    if dotation_projet.dotation == DOTATION_DSIL:
        assert dotation_projet.detr_avis_commission is None
    else:
        assert dotation_projet.detr_avis_commission is False


@pytest.mark.django_db
def test_compute_taux_from_montant():
    projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
    )
    taux = DotationProjetService.compute_taux_from_montant(projet, 10_000)
    assert taux == 10

    projet = DotationProjetFactory(
        assiette=50_000,
    )
    taux = DotationProjetService.compute_taux_from_montant(projet, 10_000)
    assert taux == 20


def test_get_projet_status():
    accepted = Dossier(ds_state=Dossier.STATE_ACCEPTE)
    en_construction = Dossier(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    en_instruction = Dossier(ds_state=Dossier.STATE_EN_INSTRUCTION)
    refused = Dossier(ds_state=Dossier.STATE_REFUSE)
    dismissed = Dossier(ds_state=Dossier.STATE_SANS_SUITE)

    assert DotationProjetService.get_projet_status(accepted) == Projet.STATUS_ACCEPTED
    assert (
        DotationProjetService.get_projet_status(en_construction)
        == Projet.STATUS_PROCESSING
    )
    assert (
        DotationProjetService.get_projet_status(en_instruction)
        == Projet.STATUS_PROCESSING
    )
    assert DotationProjetService.get_projet_status(refused) == Projet.STATUS_REFUSED
    assert DotationProjetService.get_projet_status(dismissed) == Projet.STATUS_DISMISSED

    dossier_unknown = Dossier(ds_state="unknown_state")
    assert DotationProjetService.get_projet_status(dossier_unknown) is None

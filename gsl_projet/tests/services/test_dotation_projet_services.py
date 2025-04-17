from decimal import Decimal

import pytest

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
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
        assert dotation_projet.status == PROJET_STATUS_ACCEPTED
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
    assert dotation_projet.status == PROJET_STATUS_DISMISSED
    assert dotation_projet.assiette == 2_000
    if dotation_projet.dotation == DOTATION_DSIL:
        assert dotation_projet.detr_avis_commission is None
    else:
        assert dotation_projet.detr_avis_commission is False


@pytest.mark.django_db
def test_compute_taux_from_montant():
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
    )
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, 10_000)
    assert taux == 10

    dotation_projet = DotationProjetFactory(
        assiette=50_000,
    )
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, 10_000)
    assert taux == 20

    dotation_projet = DotationProjetFactory()
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, 10_000)
    assert taux == 0


def test_get_dotation_projet_status_from_dossier():
    accepted = Dossier(ds_state=Dossier.STATE_ACCEPTE)
    en_construction = Dossier(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    en_instruction = Dossier(ds_state=Dossier.STATE_EN_INSTRUCTION)
    refused = Dossier(ds_state=Dossier.STATE_REFUSE)
    dismissed = Dossier(ds_state=Dossier.STATE_SANS_SUITE)

    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(accepted)
        == PROJET_STATUS_ACCEPTED
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(en_construction)
        == PROJET_STATUS_PROCESSING
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(en_instruction)
        == PROJET_STATUS_PROCESSING
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(refused)
        == PROJET_STATUS_REFUSED
    )
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(dismissed)
        == PROJET_STATUS_DISMISSED
    )

    dossier_unknown = Dossier(ds_state="unknown_state")
    assert (
        DotationProjetService.get_dotation_projet_status_from_dossier(dossier_unknown)
        is None
    )


@pytest.mark.parametrize(
    "montant, assiette_or_cout_total, should_raise_exception",
    [
        (50, 100, False),  # Valid montant
        (0, 100, False),  # Valid montant at lower bound
        (100, 100, False),  # Valid montant at upper bound
        (-1, 100, True),  # Invalid montant below lower bound
        (101, 100, True),  # Invalid montant above upper bound
        (None, 100, True),  # Invalid montant as None
        ("invalid", 100, True),  # Invalid montant as string
    ],
)
@pytest.mark.django_db
def test_validate_montant(montant, assiette_or_cout_total, should_raise_exception):
    dotation_projet_with_assiette = DotationProjetFactory(
        assiette=assiette_or_cout_total
    )
    dotation_projet_without_assiette = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=assiette_or_cout_total
    )

    if should_raise_exception:
        with pytest.raises(
            ValueError,
            match=(
                f"Montant {montant} must be greatear or equal to 0 and less than or "
                f"equal to {dotation_projet_with_assiette.assiette_or_cout_total}"
            ),
        ):
            DotationProjetService.validate_montant(
                montant, dotation_projet_with_assiette
            )

        with pytest.raises(
            ValueError,
            match=(
                f"Montant {montant} must be greatear or equal to 0 and less than or "
                f"equal to {dotation_projet_without_assiette.assiette_or_cout_total}"
            ),
        ):
            DotationProjetService.validate_montant(
                montant, dotation_projet_with_assiette
            )
    else:
        DotationProjetService.validate_montant(montant, dotation_projet_with_assiette)
        DotationProjetService.validate_montant(
            montant, dotation_projet_without_assiette
        )


test_data = (
    (10_000, 30_000, 33.33),
    (10_000, 0, 0),
    (10_000, 10_000, 100),
    (100_000, 10_000, 100),
    (10_000, -3_000, 0),
    (0, 0, 0),
    (Decimal(0), Decimal(0), 0),
    (0, None, 0),
    (None, 0, 0),
    (1_000, None, 0),
    (None, 4_000, 0),
)


@pytest.mark.parametrize("montant, assiette, expected_taux", test_data)
@pytest.mark.django_db
def test_compute_taux_from_montant_with_various_assiettes(
    assiette, montant, expected_taux
):
    dotation_projet = DotationProjetFactory(assiette=assiette)
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, montant)
    assert taux == round(Decimal(expected_taux), 2)


@pytest.mark.parametrize("montant, cout_total, expected_taux", test_data)
@pytest.mark.django_db
def test_compute_taux_from_montant_with_various_cout_total(
    cout_total, montant, expected_taux
):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__finance_cout_total=cout_total
    )
    taux = DotationProjetService.compute_taux_from_montant(dotation_projet, montant)
    assert taux == round(Decimal(expected_taux), 2)


@pytest.mark.parametrize(
    "taux, should_raise_exception",
    [
        (50, False),
        (0, False),
        (100, False),
        (-1, True),
        (101, True),
        (None, True),
        ("invalid", True),
    ],
)
def test_validate_taux(taux, should_raise_exception):
    if should_raise_exception:
        with pytest.raises(ValueError, match=f"Taux {taux} must be between 0 and 100"):
            DotationProjetService.validate_taux(taux)
    else:
        DotationProjetService.validate_taux(taux)

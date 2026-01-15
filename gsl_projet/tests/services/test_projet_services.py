import logging
from unittest import mock

import pytest

from gsl_core.tests.factories import (
    AdresseFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.services import DsService
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.services.projet_services import ProjetService as ps
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory


@pytest.mark.django_db
def test_create_or_update_projet_from_dossier_with_existing_projet():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = ProjetFactory(dossier_ds=dossier)

    assert ps.create_or_update_from_ds_dossier(dossier) == projet


@pytest.mark.django_db
def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    demandeur_commune = dossier.ds_demandeur.address.commune
    perimetre = PerimetreArrondissementFactory(
        arrondissement=demandeur_commune.arrondissement,
    )
    assert (
        dossier.ds_demandeur.address.commune.arrondissement == perimetre.arrondissement
    )
    assert dossier.ds_demandeur.address.commune.departement == perimetre.departement

    projet = ps.create_or_update_from_ds_dossier(dossier)

    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse

    assert projet.perimetre == dossier.get_projet_perimetre()

    other_projet = ps.create_or_update_from_ds_dossier(dossier)
    assert other_projet == projet


@pytest.fixture
def projets_with_finance_cout_total():
    projets = []
    for amount in (15_000, 25_000):
        projets.append(
            ProjetFactory(
                dossier_ds__finance_cout_total=amount,
            )
        )
    return projets


@pytest.fixture
def other_projets():
    ProjetFactory(
        dossier_ds__finance_cout_total=50_000,
    )


@pytest.mark.django_db
def test_get_total_cost(projets_with_finance_cout_total):
    qs = Projet.objects.all()
    assert ps.get_total_cost(qs) == 40_000


@pytest.mark.django_db
def test_get_same_total_cost_even_if_there_is_other_projets(
    projets_with_finance_cout_total,
    other_projets,
):
    projet_ids = [projet.id for projet in projets_with_finance_cout_total]
    qs = Projet.objects.filter(id__in=projet_ids).all()
    assert ps.get_total_cost(qs) == 40_000


@pytest.mark.django_db
def test_get_total_amount_granted():
    dotation_projet_1 = DotationProjetFactory()
    dotation_projet_2 = DotationProjetFactory()
    dotation_projet_3 = DotationProjetFactory()
    _dotation_projet_4 = DotationProjetFactory()

    ProgrammationProjetFactory(
        dotation_projet=dotation_projet_1,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=10_000,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet_2,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=20_000,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet_3,
        status=ProgrammationProjet.STATUS_REFUSED,
        montant=0,
    )

    qs = Projet.objects.all()
    assert ps.get_total_amount_granted(qs) == 30_000


@pytest.fixture
def projets_with_demande_montant() -> list[Projet]:
    projets = []
    for amount in (15_000, 25_000):
        projets.append(
            ProjetFactory(
                dossier_ds__demande_montant=amount,
            )
        )
    return projets


@pytest.fixture
def other_projets_with_demande_montant() -> None:
    for amount in (10_000, 2_000):
        ProjetFactory(
            dossier_ds__demande_montant=amount,
        )


@pytest.mark.django_db
def test_get_total_amount_asked(
    projets_with_demande_montant,
    other_projets_with_demande_montant,
):
    projet_ids = [projet.id for projet in projets_with_demande_montant]
    qs = Projet.objects.filter(id__in=projet_ids).all()
    assert ps.get_total_amount_asked(qs) == 15_000 + 25_000


@pytest.fixture
def create_projets():
    epci_nature = NaturePorteurProjetFactory(label="EPCI")
    commune_nature = NaturePorteurProjetFactory(label="Communes")
    for i in (49, 50, 100, 150, 151):
        ProjetFactory(
            assiette=i,
            dossier_ds=DossierFactory(
                demande_dispositif_sollicite="DETR",
                porteur_de_projet_nature=epci_nature,
            ),
        )
        ProjetFactory(
            assiette=i,
            dossier_ds=DossierFactory(
                demande_dispositif_sollicite="DETR",
                porteur_de_projet_nature=commune_nature,
            ),
        )
        ProjetFactory(
            assiette=i, dossier_ds=DossierFactory(demande_dispositif_sollicite="DSIL")
        )


# @pytest.mark.django_db
# def test_add_ordering_to_projets_qs():
#     projet1 = ProjetFactory(
#         dossier_ds__finance_cout_total=100,
#         dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 1, tzinfo=UTC),
#         demandeur__name="Beaune",
#     )
#     projet2 = ProjetFactory(
#         dossier_ds__finance_cout_total=200,
#         dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 2, tzinfo=UTC),
#         demandeur__name="Dijon",
#     )
#     projet3 = ProjetFactory(
#         dossier_ds__finance_cout_total=150,
#         dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 3, tzinfo=UTC),
#         demandeur__name="Auxonne",
#     )

#     ordering = "date_desc"
#     qs = Projet.objects.all()
#     ordered_qs = ps.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet3, projet2, projet1]

#     ordering = "date_asc"
#     ordered_qs = ps.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet1, projet2, projet3]

#     ordering = "cout_desc"
#     ordered_qs = ps.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet2, projet3, projet1]

#     ordering = "cout_asc"
#     ordered_qs = ps.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet1, projet3, projet2]

#     ordering = "demandeur_desc"
#     ordered_qs = ps.add_ordering_to_projets_qs(qs, ordering)
#     assert list(ordered_qs) == [projet2, projet1, projet3]

#     ordering = "demandeur_asc"
#     ordered_qs = ps.add_ordering_to_projets_qs(qs, ordering)
#     assert list(ordered_qs) == [projet3, projet1, projet2]


@pytest.mark.parametrize(
    "annotation_value, expected_result",
    [
        (True, True),
        (False, False),
        (None, False),
    ],
)
@pytest.mark.parametrize(
    "annotation_field_name",
    (
        "annotations_is_qpv",
        "annotations_is_crte",
        "annotations_is_budget_vert",
        "annotations_is_frr",
        "annotations_is_acv",
        "annotations_is_pvd",
        "annotations_is_va",
        "annotations_is_autre_zonage_local",
        "annotations_is_contrat_local",
    ),
)
@pytest.mark.django_db
def test_get_boolean_value(
    annotation_field_name,
    annotation_value,
    expected_result,
):
    dossier = DossierFactory()
    setattr(dossier, annotation_field_name, annotation_value)
    assert ps._get_boolean_value(dossier, annotation_field_name) == expected_result


@pytest.fixture
def projet():
    return ProjetFactory()


@pytest.fixture
def user():
    return CollegueFactory()


@pytest.mark.django_db
def test_update_dotation_with_no_value(projet, user, caplog):
    with caplog.at_level(logging.WARNING):
        ps.update_dotation(projet, [], user)
    assert "Projet must have at least one dotation" in caplog.text
    assert projet.dotations == []


@pytest.mark.django_db
def test_update_dotation_with_more_than_2_values(projet, user, caplog):
    with caplog.at_level(logging.WARNING):
        ps.update_dotation(projet, [DOTATION_DETR, DOTATION_DSIL, "unknown"], user)
    assert "Projet can't have more than two dotations" in caplog.text
    assert projet.dotations == []


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(
    DotationProjetService, "create_simulation_projets_from_dotation_projet"
)
@pytest.mark.django_db
def test_update_dotation_from_one_dotation_to_another(
    mock_create_simulation_projets, dotation, projet, user
):
    original_dotation_projet = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )
    SimulationProjetFactory.create_batch(3, dotation_projet=original_dotation_projet)
    ProgrammationProjetFactory.create(dotation_projet=original_dotation_projet)

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    ps.update_dotation(projet, [new_dotation], user)

    assert projet.dotations == [new_dotation]
    assert projet.dotationprojet_set.count() == 1
    dotation_projet = projet.dotationprojet_set.first()

    assert mock_create_simulation_projets.call_count == 1
    mock_create_simulation_projets.assert_called_once_with(dotation_projet)

    # Check that the old dotation_projet is deleted
    assert DotationProjet.objects.filter(pk=original_dotation_projet.pk).count() == 0
    assert SimulationProjet.objects.count() == 0
    assert ProgrammationProjet.objects.count() == 0


@pytest.mark.parametrize("original_dotation", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(
    DotationProjetService, "create_simulation_projets_from_dotation_projet"
)
@pytest.mark.django_db
def test_update_dotation_from_one_to_two(
    mock_create_simulation_projets, original_dotation, projet, user
):
    original_dotation_projet = DotationProjetFactory(
        projet=projet, dotation=original_dotation
    )
    SimulationProjetFactory.create_batch(3, dotation_projet=original_dotation_projet)
    ProgrammationProjetFactory.create(dotation_projet=original_dotation_projet)

    ps.update_dotation(projet, [DOTATION_DETR, DOTATION_DSIL], user)

    assert projet.dotationprojet_set.count() == 2
    assert all(
        dotation in projet.dotations for dotation in {DOTATION_DETR, DOTATION_DSIL}
    )
    new_dotation_projet = projet.dotationprojet_set.exclude(
        pk=original_dotation_projet.pk
    ).first()
    mock_create_simulation_projets.assert_called_once_with(new_dotation_projet)
    assert new_dotation_projet.status == PROJET_STATUS_PROCESSING
    assert new_dotation_projet.assiette is None
    assert new_dotation_projet.detr_avis_commission is None


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_accepted_dotation_calls_ds_service(
    mock_update_ds_annotations,
    dotation,
    projet,
    user,
):
    """Test that removing an ACCEPTED dotation_projet calls DS service"""
    accepted_dotation_projet = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_ACCEPTED
    )

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    ps.update_dotation(projet, [new_dotation], user)

    # Verify DS service was called with correct parameters
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet.dossier_ds,
        user=user,
        dotations_to_be_checked=accepted_dotation_projet.other_accepted_dotations,
    )

    # Verify the dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=accepted_dotation_projet.pk).count() == 0


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_processing_dotation_no_ds_service_call(
    mock_update_ds_annotations,
    dotation,
    projet,
    user,
):
    """Test that removing a PROCESSING dotation_projet does NOT call DS service"""
    processing_dotation_projet = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    ps.update_dotation(projet, [new_dotation], user)

    # Verify DS service was NOT called
    mock_update_ds_annotations.assert_not_called()

    # Verify the dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=processing_dotation_projet.pk).count() == 0


@pytest.mark.parametrize("dotation_to_remove", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_accepted_dotation_keeps_other_accepted_dotations_in_dn(
    mock_update_ds_annotations,
    dotation_to_remove,
    projet,
    user,
):
    """Test that removing an ACCEPTED dotation_projet passes other_accepted_dotations correctly"""
    # Create two accepted dotations
    dotation_to_keep = (
        DOTATION_DSIL if dotation_to_remove == DOTATION_DETR else DOTATION_DETR
    )
    accepted_dotation_to_remove = DotationProjetFactory(
        projet=projet, dotation=dotation_to_remove, status=PROJET_STATUS_ACCEPTED
    )
    accepted_dotation_to_keep = DotationProjetFactory(
        projet=projet, dotation=dotation_to_keep, status=PROJET_STATUS_ACCEPTED
    )

    # Remove one dotation
    ps.update_dotation(projet, [dotation_to_keep], user)

    # Verify DS service was called with the other accepted dotation
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet.dossier_ds,
        user=user,
        dotations_to_be_checked=[dotation_to_keep],
    )

    # Verify the removed dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_remove.pk).count() == 0
    # Verify the kept dotation_projet still exists
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_keep.pk).count() == 1


@pytest.mark.parametrize("dotation_to_remove", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_accepted_dotation_with_processing_dotation(
    mock_update_ds_annotations,
    dotation_to_remove,
    projet,
    user,
):
    """Test that removing an ACCEPTED dotation_projet ignores PROCESSING dotations in other_accepted_dotations"""
    # Create one accepted and one processing dotation
    dotation_to_keep = (
        DOTATION_DSIL if dotation_to_remove == DOTATION_DETR else DOTATION_DETR
    )
    accepted_dotation_to_remove = DotationProjetFactory(
        projet=projet, dotation=dotation_to_remove, status=PROJET_STATUS_ACCEPTED
    )
    processing_dotation_to_keep = DotationProjetFactory(
        projet=projet, dotation=dotation_to_keep, status=PROJET_STATUS_PROCESSING
    )

    # Remove the accepted dotation
    ps.update_dotation(projet, [dotation_to_keep], user)

    # Verify DS service was called with empty list (no other accepted dotations)
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet.dossier_ds,
        user=user,
        dotations_to_be_checked=[],
    )

    # Verify the removed dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_remove.pk).count() == 0
    # Verify the kept dotation_projet still exists
    assert DotationProjet.objects.filter(pk=processing_dotation_to_keep.pk).count() == 1


@pytest.mark.parametrize("dotation_to_remove", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_with_dn_error_cancel_update(
    mock_update_ds_annotations,
    dotation_to_remove,
    projet,
    user,
):
    """Test that removing an ACCEPTED dotation_projet cancels the update if there is an error in the DS service"""
    # Create one accepted and one processing dotation
    dotation_to_keep = (
        DOTATION_DSIL if dotation_to_remove == DOTATION_DETR else DOTATION_DETR
    )
    accepted_dotation_to_remove = DotationProjetFactory(
        projet=projet, dotation=dotation_to_remove, status=PROJET_STATUS_ACCEPTED
    )
    processing_dotation_to_keep = DotationProjetFactory(
        projet=projet, dotation=dotation_to_keep, status=PROJET_STATUS_PROCESSING
    )
    mock_update_ds_annotations.side_effect = DsServiceException("Error in DS service")

    # Remove the accepted dotation
    with pytest.raises(DsServiceException):
        ps.update_dotation(projet, [dotation_to_keep], user)

    # Verify DS service was called with empty list (no other accepted dotations)
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet.dossier_ds,
        user=user,
        dotations_to_be_checked=[],
    )

    # Verify the removed dotation_projet still exists
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_remove.pk).count() == 1
    # Verify the kept dotation_projet still exists
    assert DotationProjet.objects.filter(pk=processing_dotation_to_keep.pk).count() == 1

import logging
from unittest import mock

import pytest

from gsl_core.tests.factories import AdresseFactory, PerimetreArrondissementFactory
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, PROJET_STATUS_PROCESSING
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.services.projet_services import ProjetService
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory


@pytest.mark.django_db
def test_create_or_update_projet_from_dossier_with_existing_projet():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = ProjetFactory(dossier_ds=dossier)

    assert ProjetService.create_or_update_from_ds_dossier(dossier) == projet


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

    projet = ProjetService.create_or_update_from_ds_dossier(dossier)

    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse
    assert projet.perimetre == perimetre

    other_projet = ProjetService.create_or_update_from_ds_dossier(dossier)
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
    assert ProjetService.get_total_cost(qs) == 40_000


@pytest.mark.django_db
def test_get_same_total_cost_even_if_there_is_other_projets(
    projets_with_finance_cout_total,
    other_projets,
):
    projet_ids = [projet.id for projet in projets_with_finance_cout_total]
    qs = Projet.objects.filter(id__in=projet_ids).all()
    assert ProjetService.get_total_cost(qs) == 40_000


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
    assert ProjetService.get_total_amount_granted(qs) == 30_000


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
    assert ProjetService.get_total_amount_asked(qs) == 15_000 + 25_000


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
#     ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet3, projet2, projet1]

#     ordering = "date_asc"
#     ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet1, projet2, projet3]

#     ordering = "cout_desc"
#     ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet2, projet3, projet1]

#     ordering = "cout_asc"
#     ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

#     assert list(ordered_qs) == [projet1, projet3, projet2]

#     ordering = "demandeur_desc"
#     ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)
#     assert list(ordered_qs) == [projet2, projet1, projet3]

#     ordering = "demandeur_asc"
#     ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)
#     assert list(ordered_qs) == [projet3, projet1, projet2]


@pytest.mark.parametrize(
    "is_in_qpv, expected_result",
    [
        (True, True),
        (False, False),
        (None, False),
    ],
)
@pytest.mark.django_db
def test_get_is_in_qpv_with_true_value(is_in_qpv, expected_result):
    dossier = DossierFactory(annotations_is_qpv=is_in_qpv)
    assert ProjetService.get_is_in_qpv(dossier) == expected_result


@pytest.mark.parametrize(
    "is_attached_to_a_crte, expected_result",
    [
        (True, True),
        (False, False),
        (None, False),
    ],
)
@pytest.mark.django_db
def test_get_is_attached_to_a_crte_with_true_value(
    is_attached_to_a_crte, expected_result
):
    dossier = DossierFactory(annotations_is_crte=is_attached_to_a_crte)
    assert ProjetService.get_is_attached_to_a_crte(dossier) == expected_result


@pytest.mark.parametrize(
    "annotations_is_budget_vert, environnement_transition_eco, expected_result",
    [
        (True, True, True),
        (True, False, True),
        (True, None, True),
        (False, True, False),
        (False, False, False),
        (False, None, False),
        (None, True, True),
        (None, False, False),
        (None, None, None),
    ],
)
@pytest.mark.django_db
def test_get_is_budget_vert(
    annotations_is_budget_vert, environnement_transition_eco, expected_result
):
    dossier = DossierFactory(
        annotations_is_budget_vert=annotations_is_budget_vert,
        environnement_transition_eco=environnement_transition_eco,
    )
    assert ProjetService.get_is_budget_vert(dossier) == expected_result


@pytest.mark.parametrize(
    "field", ("annotations_dotation", "demande_dispositif_sollicite")
)
@pytest.mark.parametrize(
    "value, expected_dotation",
    [
        ("DETR", [DOTATION_DETR]),
        ("DSIL", [DOTATION_DSIL]),
        ("[DETR, DSIL]", [DOTATION_DETR, DOTATION_DSIL]),
        ("DETR et DSIL", [DOTATION_DETR, DOTATION_DSIL]),
        ("['DETR', 'DSIL', 'DETR et DSIL']", [DOTATION_DETR, DOTATION_DSIL]),
    ],
)
@pytest.mark.django_db
def test_get_dotations_from_field(field, value, expected_dotation):
    projet = ProjetFactory()
    setattr(projet.dossier_ds, field, value)
    dotation = ProjetService.get_dotations_from_field(projet, field)
    assert dotation == expected_dotation


@pytest.fixture
def projet():
    return ProjetFactory()


@pytest.mark.django_db
def test_update_dotation_with_no_value(projet, caplog):
    with caplog.at_level(logging.WARNING):
        ProjetService.update_dotation(projet, [])
    assert f"Projet {projet.__str__()} must have at least one dotation" in caplog.text
    assert projet.dotations == []


@pytest.mark.django_db
def test_update_dotation_with_more_than_2_values(projet, caplog):
    with caplog.at_level(logging.WARNING):
        ProjetService.update_dotation(projet, [DOTATION_DETR, DOTATION_DSIL, "unknown"])
    assert (
        f"Projet {projet.__str__()} can't have more than two dotations" in caplog.text
    )
    assert projet.dotations == []


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@mock.patch.object(
    DotationProjetService, "create_simulation_projets_from_dotation_projet"
)
@pytest.mark.django_db
def test_update_dotation_from_one_dotation_to_another(
    mock_create_simulation_projets, dotation, projet
):
    original_dotation_projet = DotationProjetFactory(projet=projet, dotation=dotation)
    SimulationProjetFactory.create_batch(3, dotation_projet=original_dotation_projet)
    ProgrammationProjetFactory.create(dotation_projet=original_dotation_projet)

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    ProjetService.update_dotation(projet, [new_dotation])

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
    mock_create_simulation_projets, original_dotation, projet
):
    original_dotation_projet = DotationProjetFactory(
        projet=projet, dotation=original_dotation
    )
    SimulationProjetFactory.create_batch(3, dotation_projet=original_dotation_projet)
    ProgrammationProjetFactory.create(dotation_projet=original_dotation_projet)

    ProjetService.update_dotation(projet, [DOTATION_DETR, DOTATION_DSIL])

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

from datetime import UTC

import pytest
from django.utils import timezone

from gsl_core.tests.factories import AdresseFactory, PerimetreArrondissementFactory
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import Projet
from gsl_projet.services.projet_services import ProjetService
from gsl_projet.tests.factories import ProjetFactory


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
                assiette=None,
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
    projet_1 = ProjetFactory()
    projet_2 = ProjetFactory()
    projet_3 = ProjetFactory()
    _projet_4 = ProjetFactory()

    ProgrammationProjetFactory(
        projet=projet_1, status=ProgrammationProjet.STATUS_ACCEPTED, montant=10_000
    )
    ProgrammationProjetFactory(
        projet=projet_2, status=ProgrammationProjet.STATUS_ACCEPTED, montant=20_000
    )
    ProgrammationProjetFactory(
        projet=projet_3, status=ProgrammationProjet.STATUS_REFUSED, montant=0
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


@pytest.mark.django_db
def test_add_ordering_to_projets_qs():
    projet1 = ProjetFactory(
        dossier_ds__finance_cout_total=100,
        dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 1, tzinfo=UTC),
        address__commune__name="Beaune",
    )
    projet2 = ProjetFactory(
        dossier_ds__finance_cout_total=200,
        dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 2, tzinfo=UTC),
        address__commune__name="Dijon",
    )
    projet3 = ProjetFactory(
        dossier_ds__finance_cout_total=150,
        dossier_ds__ds_date_depot=timezone.datetime(2023, 1, 3, tzinfo=UTC),
        address__commune__name="Auxonne",
    )

    ordering = "date_desc"
    qs = Projet.objects.all()
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet3, projet2, projet1]

    ordering = "date_asc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet1, projet2, projet3]

    ordering = "cout_desc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet2, projet3, projet1]

    ordering = "cout_asc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)

    assert list(ordered_qs) == [projet1, projet3, projet2]

    ordering = "commune_desc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)
    assert list(ordered_qs) == [projet2, projet1, projet3]

    ordering = "commune_asc"
    ordered_qs = ProjetService.add_ordering_to_projets_qs(qs, ordering)
    assert list(ordered_qs) == [projet3, projet1, projet2]


# TODO pr_dotattion move this in dotation_projet_services
@pytest.mark.django_db
def test_get_avis_commission_detr_with_accepted_state_and_detr_dispositif():
    dossier = DossierFactory(
        ds_state=Dossier.STATE_ACCEPTE,
        demande_dispositif_sollicite="DETR",
    )
    assert ProjetService.get_avis_commission_detr(dossier) is True


@pytest.mark.django_db
def test_get_avis_commission_detr_with_accepted_state_and_non_detr_dispositif():
    dossier = DossierFactory(
        ds_state=Dossier.STATE_ACCEPTE,
        demande_dispositif_sollicite="DSIL",
    )
    assert ProjetService.get_avis_commission_detr(dossier) is None


@pytest.mark.django_db
def test_get_avis_commission_detr_with_non_accepted_state_and_detr_dispositif():
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        demande_dispositif_sollicite="DETR",
    )
    assert ProjetService.get_avis_commission_detr(dossier) is None


@pytest.mark.django_db
def test_get_avis_commission_detr_with_non_accepted_state_and_non_detr_dispositif():
    dossier = DossierFactory(
        ds_state=Dossier.STATE_REFUSE,
        demande_dispositif_sollicite="DSIL",
    )
    assert ProjetService.get_avis_commission_detr(dossier) is None


@pytest.mark.parametrize(
    "ds_state, dispositif, expected_result",
    [
        (Dossier.STATE_ACCEPTE, "DETR", True),
        (Dossier.STATE_ACCEPTE, "['DSIL', 'DETR']", True),
        (Dossier.STATE_ACCEPTE, "DSIL", None),
        (Dossier.STATE_EN_INSTRUCTION, "DETR", None),
        (Dossier.STATE_REFUSE, "DSIL", None),
        (Dossier.STATE_SANS_SUITE, "DETR", None),
    ],
)
@pytest.mark.django_db
def test_get_avis_commission_detr(ds_state, dispositif, expected_result):
    dossier = DossierFactory(
        ds_state=ds_state,
        demande_dispositif_sollicite=dispositif,
    )
    assert ProjetService.get_avis_commission_detr(dossier) == expected_result


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

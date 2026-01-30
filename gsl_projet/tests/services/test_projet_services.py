import pytest

from gsl_core.tests.factories import (
    AdresseFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.models import Projet
from gsl_projet.services.projet_services import ProjetService as ps
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


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

    assert projet.perimetre == dossier.perimetre

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


@pytest.mark.django_db
def test_create_or_update_projet_syncs_autre_zonage_local():
    """Test that autre_zonage_local is synced from DN dossier to projet"""
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    dossier.annotations_is_autre_zonage_local = True
    dossier.annotations_autre_zonage_local = "Zonage Test ABC"
    dossier.save()

    projet = ps.create_or_update_from_ds_dossier(dossier)

    assert projet.is_autre_zonage_local is True
    assert projet.autre_zonage_local == "Zonage Test ABC"


@pytest.mark.django_db
def test_create_or_update_projet_syncs_contrat_local():
    """Test that contrat_local is synced from DN dossier to projet"""
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    dossier.annotations_is_contrat_local = True
    dossier.annotations_contrat_local = "Contrat Test XYZ"
    dossier.save()

    projet = ps.create_or_update_from_ds_dossier(dossier)

    assert projet.is_contrat_local is True
    assert projet.contrat_local == "Contrat Test XYZ"


@pytest.mark.django_db
def test_create_or_update_projet_syncs_both_text_fields():
    """Test that both autre_zonage_local and contrat_local are synced from DN dossier"""
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    dossier.annotations_is_autre_zonage_local = True
    dossier.annotations_autre_zonage_local = "Zonage ABC"
    dossier.annotations_is_contrat_local = True
    dossier.annotations_contrat_local = "Contrat XYZ"
    dossier.save()

    projet = ps.create_or_update_from_ds_dossier(dossier)

    assert projet.is_autre_zonage_local is True
    assert projet.autre_zonage_local == "Zonage ABC"
    assert projet.is_contrat_local is True
    assert projet.contrat_local == "Contrat XYZ"


@pytest.mark.django_db
def test_create_or_update_projet_syncs_empty_text_fields():
    """Test that empty text fields are synced correctly when checkboxes are False"""
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    dossier.annotations_is_autre_zonage_local = False
    dossier.annotations_autre_zonage_local = ""
    dossier.annotations_is_contrat_local = False
    dossier.annotations_contrat_local = ""
    dossier.save()

    projet = ps.create_or_update_from_ds_dossier(dossier)

    assert projet.is_autre_zonage_local is False
    assert projet.autre_zonage_local == ""
    assert projet.is_contrat_local is False
    assert projet.contrat_local == ""


@pytest.mark.django_db
def test_update_existing_projet_syncs_text_fields():
    """Test that updating an existing projet syncs text fields from DN"""
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = ProjetFactory(dossier_ds=dossier)

    # Update dossier with new text field values
    dossier.annotations_is_autre_zonage_local = True
    dossier.annotations_autre_zonage_local = "Updated Zonage"
    dossier.annotations_is_contrat_local = True
    dossier.annotations_contrat_local = "Updated Contrat"
    dossier.save()

    updated_projet = ps.create_or_update_from_ds_dossier(dossier)

    assert updated_projet == projet  # Same instance
    assert updated_projet.is_autre_zonage_local is True
    assert updated_projet.autre_zonage_local == "Updated Zonage"
    assert updated_projet.is_contrat_local is True
    assert updated_projet.contrat_local == "Updated Contrat"

from datetime import UTC

import pytest
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from gsl_core.models import Collegue, Departement
from gsl_core.tests.factories import (
    ArrondissementFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreFactory,
    PerimetreRegionalFactory,
    RequestFactory,
)
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_demarches_simplifiees.tests.factories import NaturePorteurProjetFactory
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import Demandeur, Projet
from gsl_projet.tests.factories import (
    DemandeurFactory,
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl_projet.utils.projet_filters import ProjetFilters
from gsl_projet.views import ProjetListView, ProjetListViewFilters

pytestmark = pytest.mark.django_db


@pytest.fixture
def dep_finistere() -> Departement:
    return DepartementFactory(name="Finistère")


@pytest.fixture
def finisterien(dep_finistere) -> Collegue:
    collegue = CollegueFactory()
    perimetre = PerimetreFactory(departement=dep_finistere)
    collegue.perimetre = perimetre
    collegue.save()
    return collegue


@pytest.fixture
def demandeur() -> Demandeur:
    return DemandeurFactory()


@pytest.fixture
def req(finisterien) -> RequestFactory:
    return RequestFactory(user=finisterien)


@pytest.fixture
def view() -> ProjetListView:
    return ProjetListView()


### Test du tri


@pytest.mark.parametrize(
    "tri_param,expected_ordering",
    [
        ("date_desc", ("-dossier_ds__ds_date_depot",)),
        ("date_asc", ("dossier_ds__ds_date_depot",)),
        ("cout_desc", ("-dossier_ds__finance_cout_total",)),
        ("cout_asc", ("dossier_ds__finance_cout_total",)),
        ("commune_desc", ("-address__commune__name",)),
        ("commune_asc", ("address__commune__name",)),
        (None, ("-dossier_ds__ds_date_depot",)),  # Test valeur par défaut
        ("invalid_value", ("-dossier_ds__ds_date_depot",)),  # Test valeur invalide
    ],
)
def test_get_ordering(req, view, tri_param, expected_ordering):
    """Test que get_ordering retourne le bon ordre selon le paramètre 'tri'"""
    request = req.get("/")
    if tri_param is not None:
        request = req.get("/", data={"tri": tri_param})

    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.query.order_by == expected_ordering


@pytest.fixture
def projets(demandeur) -> list[Projet]:
    projet0 = ProjetFactory(
        dossier_ds__ds_date_depot=timezone.datetime(2024, 9, 1, tzinfo=UTC),
        dossier_ds__finance_cout_total=1000,
        address__commune__name="Commune A",
        demandeur=demandeur,
    )
    projet1 = ProjetFactory(
        dossier_ds__ds_date_depot=timezone.datetime(2024, 9, 2, tzinfo=UTC),
        dossier_ds__finance_cout_total=2000,
        address__commune__name="Commune B",
        demandeur=demandeur,
    )
    return [projet0, projet1]


@pytest.mark.parametrize(
    "tri_param,expected_ordering",
    [
        ("date_desc", "1-0"),
        ("date_asc", "0-1"),
        ("cout_desc", "1-0"),
        ("cout_asc", "0-1"),
        ("commune_desc", "1-0"),
        ("commune_asc", "0-1"),
        ("", "1-0"),
        ("invalid_value", "1-0"),
    ],
)
def test_projets_ordering(req, view, projets, tri_param, expected_ordering):
    request = req.get("/", data={"tri": tri_param})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs
    projets_lis = [projets[1], projets[0]] if expected_ordering == "1-0" else projets
    assert list(qs) == projets_lis


### Test du filtre par dispositif


@pytest.fixture
def projets_detr(demandeur) -> list[Projet]:
    dotation_projets = DetrProjetFactory.create_batch(
        3,
        projet__demandeur=demandeur,
    )
    return [dp.projet for dp in dotation_projets]


@pytest.fixture
def projets_dsil(demandeur) -> list[Projet]:
    dotation_projets = DsilProjetFactory.create_batch(
        2,
        projet__demandeur=demandeur,
    )
    return [dp.projet for dp in dotation_projets]


@pytest.fixture
def projets_with_double_dotations_values(demandeur) -> list[Projet]:
    projets = []
    for _ in range(4):
        detr_projet = DetrProjetFactory(projet__demandeur=demandeur)
        DsilProjetFactory(projet=detr_projet.projet)
        projets.append(detr_projet.projet)
    return projets


@pytest.fixture
def projets_with_other_dotations_values(demandeur) -> list[Projet]:
    return [
        ProjetFactory(
            dossier_ds__demande_dispositif_sollicite=dotation, demandeur=demandeur
        )
        for dotation in (
            "",
            "Fond vert",
        )
    ]


def test_filter_by_dotation_only_detr(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DETR"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 3
    assert all(p.dotationprojet_set.count() == 1 for p in qs)
    assert all(p.dotationprojet_set.first().dotation == DOTATION_DETR for p in qs)


def test_filter_by_dotation_only_dsil(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DSIL"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 2
    assert all(p.dotationprojet_set.count() == 1 for p in qs)
    assert all(p.dotationprojet_set.first().dotation == DOTATION_DSIL for p in qs)


def test_filter_by_dotation_detr_and_dsil(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DETR", "DSIL"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 3 + 2
    assert all(p.dotationprojet_set.count() == 1 for p in qs)
    assert qs.filter(dotationprojet__dotation=DOTATION_DETR).count() == 3
    assert qs.filter(dotationprojet__dotation=DOTATION_DSIL).count() == 2


def test_filter_by_dotation_only_detr_dsil(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DETR_et_DSIL"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 4
    assert (
        sum(
            1
            for projet in qs
            if "DETR" in projet.dotations and "DSIL" in projet.dotations
        )
        == 4
    )


def test_filter_by_dotation_detr_and_detr_dsil(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DETR", "DETR_et_DSIL"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 3 + 4
    assert sum(1 for projet in qs if "DETR" in projet.dotations) == 7
    assert (
        sum(
            1
            for projet in qs
            if "DETR" in projet.dotations and "DSIL" not in projet.dotations
        )
        == 3
    )
    assert sum(1 for projet in qs if "DSIL" in projet.dotations) == 4


def test_filter_by_dotation_dsil_and_detr_dsil(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DSIL", "DETR_et_DSIL"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 2 + 4
    assert all("DSIL" in projet.dotations for projet in qs)
    assert sum(1 for projet in qs if "DETR" not in projet.dotations) == 2
    assert sum(1 for projet in qs if "DETR" in projet.dotations) == 4


def test_filter_by_dotation_detr_and_dsil_and_detr_dsil(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/", data={"dotation": ["DETR", "DSIL", "DETR_et_DSIL"]})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert Projet.objects.count() == 11

    assert qs.count() == 3 + 2 + 4
    assert sum(1 for projet in qs if "DETR" in projet.dotations) == 7
    assert sum(1 for projet in qs if "DETR" not in projet.dotations) == 2
    assert sum(1 for projet in qs if "DSIL" in projet.dotations) == 6
    assert sum(1 for projet in qs if "DSIL" not in projet.dotations) == 3
    assert sum(1 for projet in qs if len(projet.dotations) == 2) == 4


def test_no_dispositif_filter(
    req,
    view,
    projets_detr,
    projets_dsil,
    projets_with_double_dotations_values,
    projets_with_other_dotations_values,
):
    request = req.get("/")
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 11


### Test du filtre par porteur


@pytest.fixture
def projets_epci(demandeur) -> list[Projet]:
    projets = []
    for epci_label in (
        "EPCI",
        "Pôle d'équilibre territorial et rural",
        "Syndicat de communes",
    ):
        nature_porteur_projet = NaturePorteurProjetFactory(
            label=epci_label, type=NaturePorteurProjet.EPCI
        )
        projets.append(
            ProjetFactory(
                demandeur=demandeur,
                dossier_ds__porteur_de_projet_nature=nature_porteur_projet,
            )
        )
    return projets


@pytest.fixture
def projets_communes(demandeur) -> list[Projet]:
    for commune_label in ("Commune",):
        nature_porteur_projet = NaturePorteurProjetFactory(
            label=commune_label, type=NaturePorteurProjet.COMMUNES
        )
        projet = ProjetFactory(
            demandeur=demandeur,
            dossier_ds__porteur_de_projet_nature=nature_porteur_projet,
        )
    return [projet]


@pytest.fixture
def projets_other(demandeur) -> list[Projet]:
    projets = []
    for commune_label in ("test_gsl", "Departement"):
        nature_porteur_projet = NaturePorteurProjetFactory(
            label=commune_label, type=NaturePorteurProjet.AUTRE
        )
        projets.append(
            ProjetFactory(
                demandeur=demandeur,
                dossier_ds__porteur_de_projet_nature=nature_porteur_projet,
            )
        )
    return projets


@pytest.fixture
def projets_unknown_projet(demandeur) -> list[Projet]:
    projets = []
    for porteur_label in ("Inconnu", "Fake", "Wrong"):
        nature_porteur_projet = NaturePorteurProjetFactory(label=porteur_label)
        projets.append(
            ProjetFactory(
                demandeur=demandeur,
                dossier_ds__porteur_de_projet_nature=nature_porteur_projet,
            )
        )
    return projets


@pytest.mark.parametrize(
    "porteur, expected_count",
    (
        ("epci", 3),
        ("communes", 1),
        ("autre", 2),
        ("inconnu", 9),
        ("", 9),
    ),
)
def test_filter_by_epci_porteur(
    req,
    view,
    projets_epci,
    projets_unknown_projet,
    projets_other,
    projets_communes,
    porteur,
    expected_count,
):
    request = req.get(f"/?porteur={porteur}")
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == expected_count


### Test du filtre par coût


@pytest.fixture
def projets_with_finance_cout_total_from_dossier_ds(
    demandeur,
) -> list[Projet]:
    return [
        ProjetFactory(
            dossier_ds__finance_cout_total=amount,
            demandeur=demandeur,
        )
        for amount in (120_000, 170_000, 220_000, 270_000, 320_000)
    ]


def test_filter_by_min_cost(
    req,
    view,
    projets_with_finance_cout_total_from_dossier_ds,
):
    request = req.get("/", data={"cout_min": 150_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 4
    assert all(150_000 <= p.dossier_ds.finance_cout_total for p in qs)


def test_filter_by_max_cost(
    req,
    view,
    projets_with_finance_cout_total_from_dossier_ds,
):
    request = req.get("/", data={"cout_max": 250_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 3
    assert all(p.dossier_ds.finance_cout_total <= 250_000 for p in qs)


def test_filter_by_cost_range(
    req,
    view,
    projets_with_finance_cout_total_from_dossier_ds,
):
    request = req.get("/", data={"cout_min": 150_000, "cout_max": 250_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 2
    assert all(100000 <= p.dossier_ds.finance_cout_total <= 250000 for p in qs)


def test_filter_with_wrong_values(
    req,
    view,
    projets_with_finance_cout_total_from_dossier_ds,
):
    request = req.get("/", data={"cout_min": "wrong"})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 5


### Test du filtre par montant retenu


@pytest.fixture
def projets_with_montant_retenu(demandeur) -> list[Projet]:
    projets = []
    for detr_montant, dsil_montant in (
        (None, 50_000),
        (50_000, 50_000),
        (100_000, 50_000),
        (100_000, 100_000),
        (150_000, 50_000),
        (150_000, 150_000),
    ):
        projet = ProjetFactory(
            demandeur=demandeur,
        )
        detr_projet = DetrProjetFactory(projet=projet)
        if detr_montant is not None:
            ProgrammationProjetFactory(
                dotation_projet=detr_projet, montant=detr_montant
            )

        dsil_projet = DsilProjetFactory(projet=projet)
        if dsil_montant is not None:
            ProgrammationProjetFactory(
                dotation_projet=dsil_projet, montant=dsil_montant
            )

        projets.append(projet)
    return projets


def test_annotate_montant_retenu(
    req,
    view,
    projets_with_montant_retenu,
):
    projet_qs = Projet.objects.all()
    projet_qs = projet_qs.annotate(
        dotation_projet_with_this_minimum_montant_retenu_count=Count(
            "dotationprojet",
            filter=Q(dotationprojet__programmation_projet__montant__gte=100_000),
        )
    )
    projet_qs = projet_qs.filter(
        dotation_projet_with_this_minimum_montant_retenu_count__gt=0
    )
    assert projet_qs.count() == 4


def test_filter_by_min_montant_retenu(
    req,
    view,
    projets_with_montant_retenu,
):
    request = req.get("/", data={"montant_retenu_min": 100_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 4
    for p in qs:
        assert any(100_000 <= dp.montant_retenu for dp in p.dotationprojet_set.all())


def test_filter_by_max_montant_retenu(
    req,
    view,
    projets_with_montant_retenu,
):
    request = req.get("/", data={"montant_retenu_max": 100_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    # (None, 50_000) ✅
    # (50_000, 50_000) ✅
    # (100_000, 50_000) ✅
    # (100_000, 100_000) ✅
    # (150_000, 50_000) ✅
    # (150_000, 150_000) ❌
    assert qs.count() == 5
    for p in qs:
        assert any(
            (dp.montant_retenu or 0.0) <= 100_000 for dp in p.dotationprojet_set.all()
        )


def test_filter_by_montant_retenu_range(
    req,
    view,
    projets_with_montant_retenu,
):
    request = req.get(
        "/", data={"montant_retenu_min": 90_000, "montant_retenu_max": 110_000}
    )
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    # (None, 50_000) ❌
    # (50_000, 50_000) ❌
    # (100_000, 50_000) ✅
    # (100_000, 100_000) ✅
    # (150_000, 50_000) ❌ Il faut qu'un dotation_projet matche les deux filtres
    # (150_000, 150_000) ❌

    assert qs.count() == 2
    for p in qs:
        assert any(
            90_000 <= dp.montant_retenu <= 110_000 for dp in p.dotationprojet_set.all()
        )


def test_filter_with_wrong_montant_retenu_values(
    req,
    view,
    projets_with_montant_retenu,
):
    request = req.get("/", data={"montant_retenu_min": "wrong"})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 6


### Test du filtre par montant demandé


@pytest.fixture
def projets_with_montant_demande(demandeur) -> list[Projet]:
    return [
        ProjetFactory(
            dossier_ds__demande_montant=amount,
            demandeur=demandeur,
        )
        for amount in (None, 30_000, 60_000, 90_000, 120_000, 150_000)
    ]


def test_filter_by_min_montant_demande(
    req,
    view,
    projets_with_montant_demande,
):
    request = req.get("/", data={"montant_demande_min": 60_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 4
    assert all(60_000 <= p.dossier_ds.demande_montant for p in qs)


def test_filter_by_max_montant_demande(
    req,
    view,
    projets_with_montant_demande,
):
    request = req.get("/", data={"montant_demande_max": 120_000})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 4
    assert all(p.dossier_ds.demande_montant <= 120_000 for p in qs)


def test_filter_by_montant_demande_range(
    req,
    view,
    projets_with_montant_demande,
):
    request = req.get(
        "/", data={"montant_demande_min": 60_000, "montant_demande_max": 120_000}
    )
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 3
    assert all(60_000 <= p.dossier_ds.demande_montant <= 120_000 for p in qs)


def test_filter_with_wrong_montant_demande_values(
    req,
    view,
    projets_with_montant_demande,
):
    request = req.get("/", data={"montant_demande_min": "wrong"})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 6


### Test du filtre par statut


@pytest.fixture
def projets_with_status(demandeur) -> list[Projet]:
    projets = []
    for status, count in (
        ("accepted", 1),
        ("processing", 2),
        ("refused", 4),
        ("dismissed", 5),
    ):
        for _ in range(count):
            projets.append(ProjetFactory(status=status, demandeur=demandeur))
    return projets


@pytest.mark.parametrize(
    "status,expected_count",
    [
        ("accepted", 1),
        ("processing", 2),
        ("refused", 4),
        ("dismissed", 5),
    ],
)
def test_filter_by_status(req, view, projets_with_status, status, expected_count):
    request = req.get("/", data={"status": status})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == expected_count
    assert qs.first().status == status


def test_get_status_placeholder(req, view, projets_with_status):
    request = req.get("/")
    view.request = request
    assert view._get_status_placeholder(ProjetListView.STATE_MAPPINGS) == "Tous"


def test_get_status_placeholder_with_status(req, view, projets_with_status):
    request = req.get("/", data={"status": ["accepted", "processing"]})
    view.request = request
    assert (
        view._get_status_placeholder(ProjetListView.STATE_MAPPINGS)
        == "✅ Accepté, 🔄 En traitement"
    )


### Test du filtre par territoire
@pytest.fixture
def perimetre_29(dep_finistere):
    return PerimetreDepartementalFactory(departement=dep_finistere)


@pytest.fixture
def perimetre_quimper(perimetre_29):
    arrondissement = ArrondissementFactory(departement=perimetre_29.departement)
    return PerimetreArrondissementFactory(arrondissement=arrondissement)


@pytest.fixture
def perimetre_brest(perimetre_29):
    arrondissement = ArrondissementFactory(departement=perimetre_29.departement)
    return PerimetreArrondissementFactory(arrondissement=arrondissement)


@pytest.fixture
def projets_29(perimetre_29, perimetre_quimper, perimetre_brest):
    return [
        ProjetFactory(perimetre=perimetre_29),
        ProjetFactory(perimetre=perimetre_quimper),
        ProjetFactory(perimetre=perimetre_brest),
    ]


def test_filter_territoire_with_a_departement_gives_all_departement_projets(
    req, view, projets_29, perimetre_29
):
    request = req.get("/", data={"territoire": perimetre_29.id})
    view.request = request
    qs = view.get_filterset(ProjetFilters).qs

    assert qs.count() == 3
    assert all(perimetre_29.contains_or_equal(p.perimetre) for p in qs)


def test_filter_territoire_with_an_arrondissement_gives_only_arrondissement_projets(
    req, view, projets_29, perimetre_quimper
):
    request = req.get("/", data={"territoire": perimetre_quimper.id})
    view.request = request
    qs = view.get_filterset(ProjetListViewFilters).qs

    assert qs.count() == 1
    assert qs.first().perimetre == perimetre_quimper


def test_filter_territoire_with_two_arrondissements_gives_only_these_arrondissement_projets(
    req, view, projets_29, perimetre_quimper, perimetre_brest
):
    request = req.get(
        "/", data={"territoire": [perimetre_quimper.id, perimetre_brest.id]}
    )
    view.request = request
    qs = view.get_filterset(ProjetListViewFilters).qs

    assert qs.count() == 2
    assert qs.first().perimetre in [perimetre_quimper, perimetre_brest]


def test_view_has_correct_territoire_choices():
    perimetre_arrondissement_A = PerimetreArrondissementFactory()
    perimetre_arrondissement_B = PerimetreArrondissementFactory()

    perimetre_departement_A = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement_A.departement,
    )
    _perimetre_departement_B = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement_B.departement,
    )
    perimetre_region_A = PerimetreRegionalFactory(
        region=perimetre_departement_A.region,
    )

    user = CollegueFactory(perimetre=perimetre_region_A)
    client = ClientWithLoggedUserFactory(user)
    url = reverse("projet:list")

    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context["territoire_choices"]) == 3
    assert response.context["territoire_choices"] == (
        perimetre_region_A,
        perimetre_departement_A,
        perimetre_arrondissement_A,
    )

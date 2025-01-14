import pytest

from gsl_core.models import Collegue, Departement
from gsl_core.tests.factories import (
    CollegueFactory,
    DepartementFactory,
    PerimetreFactory,
    RequestFactory,
)
from gsl_demarches_simplifiees.tests.factories import NaturePorteurProjetFactory
from gsl_projet.models import Demandeur, Projet
from gsl_projet.tests.factories import DemandeurFactory, ProjetFactory
from gsl_projet.views import ProjetListView


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
def demandeur(dep_finistere) -> Demandeur:
    return DemandeurFactory(departement=dep_finistere)


@pytest.fixture
def req(finisterien) -> RequestFactory:
    return RequestFactory(user=finisterien)


@pytest.fixture
def view() -> ProjetListView:
    return ProjetListView()


### Test du tri


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tri_param,expected_ordering",
    [
        ("date_desc", "-dossier_ds__ds_date_depot"),
        ("date_asc", "dossier_ds__ds_date_depot"),
        ("cout_desc", "-dossier_ds__finance_cout_total"),
        ("cout_asc", "dossier_ds__finance_cout_total"),
        ("commune_desc", "-address__commune__name"),
        ("commune_asc", "address__commune__name"),
        (None, None),  # Test valeur par défaut
        ("invalid_value", None),  # Test valeur invalide
    ],
)
def test_get_ordering(req, view, tri_param, expected_ordering):
    """Test que get_ordering retourne le bon ordre selon le paramètre 'tri'"""
    request = req.get("/")
    if tri_param is not None:
        request = req.get(f"/?tri={tri_param}")

    view.request = request

    assert view.get_ordering() == expected_ordering


@pytest.fixture
def projets(demandeur) -> list[Projet]:
    projet0 = ProjetFactory(
        dossier_ds__ds_date_depot="2024-09-01",
        dossier_ds__finance_cout_total=1000,
        address__commune__name="Commune A",
        demandeur=demandeur,
    )
    projet1 = ProjetFactory(
        dossier_ds__ds_date_depot="2024-09-02",
        dossier_ds__finance_cout_total=2000,
        address__commune__name="Commune B",
        demandeur=demandeur,
    )
    return [projet0, projet1]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tri_param,expected_ordering",
    [
        ("date_desc", "1-0"),
        ("date_asc", "0-1"),
        ("cout_desc", "1-0"),
        ("cout_asc", "0-1"),
        ("commune_desc", "1-0"),
        ("commune_asc", "0-1"),
        ("", "0-1"),
        ("invalid_value", "0-1"),
    ],
)
def test_projets_ordering(req, view, projets, tri_param, expected_ordering):
    request = req.get("/?tri=" + tri_param)
    view.request = request
    qs = view.get_queryset()
    projets_lis = [projets[1], projets[0]] if expected_ordering == "1-0" else projets
    assert list(qs) == projets_lis


### Test du filtre par dispositif


@pytest.fixture
def projets_detr(demandeur) -> list[Projet]:
    return [
        ProjetFactory(
            dossier_ds__demande_dispositif_sollicite="DETR",
            demandeur=demandeur,
        )
        for _ in range(3)
    ]


@pytest.fixture
def projets_dsil(demandeur) -> list[Projet]:
    return [
        ProjetFactory(
            dossier_ds__demande_dispositif_sollicite="DSIL",
            demandeur=demandeur,
        )
        for _ in range(2)
    ]


@pytest.mark.django_db
def test_filter_by_dispositif(req, view, projets_detr, projets_dsil):
    request = req.get("/?dispositif=DETR")
    view.request = request
    qs = view.get_queryset()

    assert Projet.objects.count() == 5

    assert qs.count() == 3
    assert all(p.dossier_ds.demande_dispositif_sollicite == "DETR" for p in qs)


@pytest.mark.django_db
def test_filter_by_dispositif_dsil(req, view, projets_detr, projets_dsil):
    request = req.get("/?dispositif=DSIL")
    view.request = request
    qs = view.get_queryset()

    assert Projet.objects.count() == 5

    assert qs.count() == 2
    assert all(p.dossier_ds.demande_dispositif_sollicite == "DSIL" for p in qs)


@pytest.mark.django_db
def test_no_dispositif_filter(req, view, projets_detr, projets_dsil):
    request = req.get("/")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 5


### Test du filtre par porteur


@pytest.fixture
def projets_epci(demandeur) -> list[Projet]:
    projets = []
    for epci_label in ["EPCI", "Pôle d'équilibre territorial et rural"]:
        nature_porteur_projet = NaturePorteurProjetFactory(label=epci_label)
        projets.append(
            ProjetFactory(
                demandeur=demandeur,
                dossier_ds__porteur_de_projet_nature=nature_porteur_projet,
            )
        )
    return projets


@pytest.fixture
def projets_communes(demandeur) -> list[Projet]:
    projets = []
    for commune_label in [
        "Commune",
        "Syndicat de communes",
        "Syndicat mixte fermé",
        "Syndicat Mixte Fermé",
    ]:
        nature_porteur_projet = NaturePorteurProjetFactory(label=commune_label)
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
    for porteur_label in ["Inconnu", "Fake", "Wrong"]:
        nature_porteur_projet = NaturePorteurProjetFactory(label=porteur_label)
        projets.append(
            ProjetFactory(
                demandeur=demandeur,
                dossier_ds__porteur_de_projet_nature=nature_porteur_projet,
            )
        )
    return projets


@pytest.mark.django_db
def test_filter_by_epci_porteur(
    req, view, projets_epci, projets_unknown_projet, projets_communes
):
    request = req.get("/?porteur=EPCI")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 2


@pytest.mark.django_db
def test_filter_by_communes_porteur(
    req, view, projets_epci, projets_unknown_projet, projets_communes
):
    request = req.get("/?porteur=Communes")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 4


@pytest.mark.django_db
def test_filter_by_epci(
    req, view, projets_epci, projets_unknown_projet, projets_communes
):
    request = req.get("/")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 9


@pytest.mark.django_db
def test_wrong_porteur_filter(
    req, view, projets_epci, projets_unknown_projet, projets_communes
):
    request = req.get("/?porteur='Fake'")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 9


### Test du filtre par coût


@pytest.fixture
def projets_with_assiette(demandeur) -> list[Projet]:
    return [
        ProjetFactory(
            assiette=amount,
            demandeur=demandeur,
        )
        for amount in [100000, 150000, 200000, 250000, 300000]
    ]


@pytest.fixture
def projets_without_assiette_but_finance_cout_total_from_dossier_ds(
    demandeur,
) -> list[Projet]:
    return [
        ProjetFactory(
            dossier_ds__finance_cout_total=amount,
            assiette=None,
            demandeur=demandeur,
        )
        for amount in [12000, 170000, 220000, 270000, 320000]
    ]


@pytest.mark.django_db
def test_filter_by_min_cost(
    req,
    view,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    request = req.get("/?cout_min=150000")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 8
    assert all(150000 <= p.assiette_or_cout_total for p in qs)


@pytest.mark.django_db
def test_filter_by_max_cost(
    req,
    view,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    request = req.get("/?cout_max=250000")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 7
    assert all(p.assiette_or_cout_total <= 250000 for p in qs)


@pytest.mark.django_db
def test_filter_by_cost_range(
    req,
    view,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    request = req.get("/?cout_min=150000&cout_max=250000")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 5
    assert all(100000 <= p.assiette_or_cout_total <= 250000 for p in qs)


@pytest.mark.django_db
def test_filter_with_wrong_values(
    req,
    view,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    request = req.get("/?cout_min=wrong")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 10

import pytest

from gsl_core.models import Collegue, Departement
from gsl_core.tests.factories import (
    CollegueFactory,
    DepartementFactory,
    PerimetreFactory,
    RequestFactory,
)
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


@pytest.fixture
def projets_detr(demandeur) -> list[Projet]:
    """Crée 3 projets DETR"""
    return [
        ProjetFactory(
            dossier_ds__demande_dispositif_sollicite="DETR",
            demandeur=demandeur,
        )
        for _ in range(3)
    ]


@pytest.fixture
def projets_dsil(demandeur) -> list[Projet]:
    """Crée 2 projets DSIL"""
    return [
        ProjetFactory(
            dossier_ds__demande_dispositif_sollicite="DSIL",
            demandeur=demandeur,
        )
        for _ in range(2)
    ]


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


@pytest.mark.django_db
def test_get_ordering_with_multiple_params(req, view):
    """Test que get_ordering fonctionne avec d'autres paramètres dans l'URL"""
    request = req.get("/?tri=commune_asc&page=2&search=test")
    view.request = request

    assert view.get_ordering() == "address__commune__name"


@pytest.mark.django_db
def test_filter_by_dispositif(req, view, projets_detr, projets_dsil):
    """Test que le filtre par dispositif fonctionne"""
    request = req.get("/?dispositif=DETR")
    view.request = request
    qs = view.get_queryset()

    assert Projet.objects.count() == 5

    assert qs.count() == 3
    assert all(p.dossier_ds.demande_dispositif_sollicite == "DETR" for p in qs)


@pytest.mark.django_db
def test_filter_by_dispositif_dsil(req, view, projets_detr, projets_dsil):
    """Test que le filtre DSIL ne retourne que les projets DSIL"""
    request = req.get("/?dispositif=DSIL")
    view.request = request
    qs = view.get_queryset()

    assert Projet.objects.count() == 5

    assert qs.count() == 2
    assert all(p.dossier_ds.demande_dispositif_sollicite == "DSIL" for p in qs)


@pytest.mark.django_db
def test_no_dispositif_filter(req, view, projets_detr, projets_dsil):
    """Test que sans filtre on obtient tous les projets"""
    request = req.get("/")
    view.request = request
    qs = view.get_queryset()

    assert qs.count() == 5

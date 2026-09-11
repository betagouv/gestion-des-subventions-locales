import pytest

from ..models import Subvention
from .factories import SubventionFactory

pytestmark = pytest.mark.django_db


def test_taux_accorde_is_none_without_montant_attribue():
    subvention = SubventionFactory(montant_attribue=None)
    assert subvention.taux_accorde is None


def test_taux_accorde_is_computed_from_montant_attribue():
    subvention = SubventionFactory(cout_total=1000, montant_attribue=500)
    assert subvention.taux_accorde == 50


def test_dgcl_duplicate_rows_are_allowed():
    kwargs = {
        "siren": "123456789",
        "exercice": 2024,
        "dispositif": "DETR",
        "intitule": "Même projet",
    }
    SubventionFactory(**kwargs)
    SubventionFactory(**kwargs)

    assert Subvention.objects.filter(siren="123456789").count() == 2


def test_fonds_vert_rows_sharing_the_dgcl_key_are_allowed():
    kwargs = {
        "siren": "123456789",
        "exercice": 2024,
        "dispositif": "FONDS VERT",
        "programme": 380,
        "intitule": "",
        "cout_total": 100,
    }
    # Beaucoup de dossiers Fonds Vert d'un même siren/exercice partagent un
    # intitulé vide : aucune contrainte modèle ne doit les empêcher de
    # coexister (l'unicité par dossier_number est désormais la tambouille de
    # l'importeur Fonds Vert, cf. gsl_stats/tasks.py).
    SubventionFactory(source=Subvention.SOURCE_FONDS_VERT, dossier_number=1, **kwargs)
    SubventionFactory(source=Subvention.SOURCE_FONDS_VERT, dossier_number=2, **kwargs)
    assert Subvention.objects.filter(siren="123456789").count() == 2

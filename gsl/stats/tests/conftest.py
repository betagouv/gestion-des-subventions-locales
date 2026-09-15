import pytest

from ..importers.utils import reset_geo_cache


@pytest.fixture(autouse=True)
def _reset_geo_cache():
    # Le cache mémoire de resolve_departement/resolve_commune ne suit pas le
    # rollback de la transaction de test : on le vide avant et après chaque
    # test pour ne jamais réutiliser des objets d'un test précédent.
    reset_geo_cache()
    yield
    reset_geo_cache()

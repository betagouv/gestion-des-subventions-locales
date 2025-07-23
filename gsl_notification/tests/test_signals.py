import pytest

from gsl_notification.models import ArreteSigne, ModeleArrete
from gsl_notification.tests.factories import ArreteSigneFactory, ModeleArreteFactory


@pytest.mark.django_db
def test_delete_file_on_post_delete(settings, tmp_path):
    # Isoler MEDIA_ROOT pour ne pas polluer les vrais fichiers.
    settings.MEDIA_ROOT = tmp_path

    arrete_signe = ArreteSigneFactory()
    storage = arrete_signe.file.storage
    name = arrete_signe.file.name

    assert storage.exists(name)

    arrete_signe.delete()

    assert not storage.exists(name)
    with pytest.raises(ArreteSigne.DoesNotExist):
        arrete_signe.refresh_from_db()


@pytest.mark.django_db
def test_delete_logo_on_modele_arrete_post_delete(settings, tmp_path):
    # Isoler MEDIA_ROOT pour ne pas polluer les vrais fichiers.
    settings.MEDIA_ROOT = tmp_path

    modele_arrete = ModeleArreteFactory()
    storage = modele_arrete.logo.storage
    name = modele_arrete.logo.name

    assert storage.exists(name)

    modele_arrete.delete()

    assert not storage.exists(name)
    with pytest.raises(ModeleArrete.DoesNotExist):
        modele_arrete.refresh_from_db()

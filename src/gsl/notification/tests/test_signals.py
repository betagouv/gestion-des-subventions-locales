import pytest

from gsl.notification.models import ModeleDocument, UploadedDocument
from gsl.notification.tests.factories import (
    AnnexeFactory,
    LettreEtArreteSignesFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)


@pytest.mark.parametrize("factory", (LettreEtArreteSignesFactory, AnnexeFactory))
@pytest.mark.django_db
def test_delete_file_on_post_delete(settings, tmp_path, factory):
    # Isoler MEDIA_ROOT pour ne pas polluer les vrais fichiers.
    settings.MEDIA_ROOT = tmp_path

    doc = factory()
    storage = doc.file.storage
    name = doc.file.name

    assert storage.exists(name)

    doc.delete()

    assert not storage.exists(name)
    with pytest.raises(UploadedDocument.DoesNotExist):
        doc.refresh_from_db()


@pytest.mark.parametrize(
    "factory", (ModeleArreteFactory, ModeleLettreNotificationFactory)
)
@pytest.mark.django_db
def test_delete_logo_on_modele_post_delete(settings, tmp_path, factory):
    # Isoler MEDIA_ROOT pour ne pas polluer les vrais fichiers.
    settings.MEDIA_ROOT = tmp_path

    modele = factory()
    storage = modele.logo.storage
    name = modele.logo.name

    assert storage.exists(name)

    modele.delete()

    assert not storage.exists(name)
    with pytest.raises(ModeleDocument.DoesNotExist):
        modele.refresh_from_db()

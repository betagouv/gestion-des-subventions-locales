import pytest

from gsl_notification.models import (
    Annexe,
    ArreteEtLettreSignes,
    ModeleArrete,
    ModeleLettreNotification,
)
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteEtLettreSignesFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)


@pytest.mark.parametrize(
    "klass, factory",
    ((ArreteEtLettreSignes, ArreteEtLettreSignesFactory), (Annexe, AnnexeFactory)),
)
@pytest.mark.django_db
def test_delete_file_on_post_delete(settings, tmp_path, klass, factory):
    # Isoler MEDIA_ROOT pour ne pas polluer les vrais fichiers.
    settings.MEDIA_ROOT = tmp_path

    doc = factory()
    storage = doc.file.storage
    name = doc.file.name

    assert storage.exists(name)

    doc.delete()

    assert not storage.exists(name)
    with pytest.raises(klass.DoesNotExist):
        doc.refresh_from_db()


@pytest.mark.parametrize(
    "klass, factory",
    (
        (ModeleArrete, ModeleArreteFactory),
        (ModeleLettreNotification, ModeleLettreNotificationFactory),
    ),
)
@pytest.mark.django_db
def test_delete_logo_on_modele_post_delete(settings, tmp_path, klass, factory):
    # Isoler MEDIA_ROOT pour ne pas polluer les vrais fichiers.
    settings.MEDIA_ROOT = tmp_path

    modele = factory()
    storage = modele.logo.storage
    name = modele.logo.name

    assert storage.exists(name)

    modele.delete()

    assert not storage.exists(name)
    with pytest.raises(klass.DoesNotExist):
        modele.refresh_from_db()

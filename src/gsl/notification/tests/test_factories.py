import pytest

from ..models import GeneratedDocument, ModeleDocument, UploadedDocument
from .factories import (
    AnnexeFactory,
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (ArreteFactory, GeneratedDocument, GeneratedDocument.Type.ARRETE),
    (LettreNotificationFactory, GeneratedDocument, GeneratedDocument.Type.LETTRE),
    (
        LettreEtArreteSignesFactory,
        UploadedDocument,
        UploadedDocument.Type.LETTRE_ET_ARRETE_SIGNES,
    ),
    (AnnexeFactory, UploadedDocument, UploadedDocument.Type.ANNEXE),
    (ModeleLettreNotificationFactory, ModeleDocument, GeneratedDocument.Type.LETTRE),
    (ModeleArreteFactory, ModeleDocument, GeneratedDocument.Type.ARRETE),
)


@pytest.mark.parametrize("factory,expected_class,expected_type", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class, expected_type):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
        assert obj.type == expected_type

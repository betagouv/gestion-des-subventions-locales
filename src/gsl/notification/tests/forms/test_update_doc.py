import pytest

from dn.sync.models import Dotation
from gsl.core.tests.factories import CollegueFactory
from gsl.notification.forms.update_doc import GeneratedDocumentForm
from gsl.notification.models import GeneratedDocument
from gsl.notification.tests.factories import (
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl.projet.constants import ProjetStatus
from gsl.projet.tests.factories import EnveloppeProjetFactory

# GeneratedDocumentForm


@pytest.mark.parametrize(
    "modele_factory",
    (ModeleArreteFactory, ModeleLettreNotificationFactory),
)
@pytest.mark.parametrize(
    "dotation",
    (Dotation.DETR, Dotation.DSIL),
)
@pytest.mark.django_db
def test_generated_document_form_valid(modele_factory, dotation):
    collegue = CollegueFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=dotation, status=ProjetStatus.ACCEPTED
    )
    modele = modele_factory(dotation=dotation)
    data = {
        "content": {"foo": "bar"},
        "created_by": collegue.id,
        "enveloppe_projet": enveloppe_projet.id,
        "modele": modele.id,
    }
    form = GeneratedDocumentForm(data, instance=GeneratedDocument(type=modele.type))
    assert form.is_valid()


@pytest.mark.django_db
def test_generated_document_form_invalid_missing_fields():
    form = GeneratedDocumentForm({})
    assert not form.is_valid()
    assert "content" in form.errors
    assert "created_by" in form.errors
    assert "enveloppe_projet" in form.errors
    assert "modele" in form.errors

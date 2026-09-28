import pytest

from gsl.core.tests.factories import CollegueFactory
from gsl.notification.forms.update_doc import ArreteForm, LettreNotificationForm
from gsl.notification.tests.factories import (
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from gsl.projet.tests.factories import EnveloppeProjetFactory

# GeneratedDocumentForm


@pytest.mark.parametrize(
    "form_class, modele_factory",
    (
        (ArreteForm, ModeleArreteFactory),
        (LettreNotificationForm, ModeleLettreNotificationFactory),
    ),
)
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DETR, DOTATION_DSIL),
)
@pytest.mark.django_db
def test_arrete_form_valid(form_class, modele_factory, dotation):
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
    form = form_class(data)
    assert form.is_valid()


@pytest.mark.parametrize(
    "form_class",
    (
        ArreteForm,
        LettreNotificationForm,
    ),
)
@pytest.mark.django_db
def test_arrete_form_invalid_missing_fields(form_class):
    form = form_class({})
    assert not form.is_valid()
    assert "content" in form.errors
    assert "created_by" in form.errors
    assert "enveloppe_projet" in form.errors
    assert "modele" in form.errors

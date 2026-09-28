import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gsl.core.tests.factories import CollegueFactory
from gsl.notification.forms.bulk_generation import (
    EXPORT_FORMAT_ONE_PDF_ALL,
    GenerateDocumentsCreateForm,
    GenerateDocumentsFormatForm,
    GenerateDocumentsModeleSelectionForm,
)
from gsl.notification.tests.factories import (
    ModeleLettreNotificationFactory,
)
from gsl.notification.utils import MENTIONS
from gsl.projet.constants import (
    ARRETE,
    DOTATION_DETR,
    ProjetStatus,
)
from gsl.projet.models import EnveloppeProjet
from gsl.projet.tests.factories import EnveloppeProjetFactory

# GenerateDocumentsFormatForm ----------------------------------------


@pytest.mark.django_db
def test_generate_documents_step3_form_exposes_with_qr_code():
    user = CollegueFactory()
    field = GenerateDocumentsFormatForm(
        user=user,
        dotation=DOTATION_DETR,
        request=None,
        document_type=ARRETE,
    ).fields["with_qr_code"]
    assert field.required is False
    assert field.initial is True


@pytest.mark.django_db
def test_generate_documents_step3_form_valid_without_qr_field_submitted():
    """An unchecked checkbox sends nothing: the form stays valid (opt-out)."""
    user = CollegueFactory()
    form = GenerateDocumentsFormatForm(
        data={"export_format": EXPORT_FORMAT_ONE_PDF_ALL},
        user=user,
        dotation=DOTATION_DETR,
        request=None,
        document_type=ARRETE,
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["with_qr_code"] is False


# GenerateDocumentsCreateForm — N+1 queries ------------------------------


def _content_with_every_mention() -> str:
    """A modele body referencing every Mention defined in gsl.notification.utils,
    so replace_mentions_in_html() walks every attribute path it can walk."""
    return "".join(
        f'<span class="mention" data-id="{mention.key}"></span>' for mention in MENTIONS
    )


def _save_documents(enveloppe_projets, modele) -> int:
    """Runs GenerateDocumentsCreateForm.save() for the given projets and
    returns the number of queries it issued."""
    form = GenerateDocumentsCreateForm(
        user=CollegueFactory(),
        dotation=DOTATION_DETR,
        request=None,
        enveloppe_projets=EnveloppeProjet.objects.filter(
            pk__in=[dp.pk for dp in enveloppe_projets]
        ),
    )
    with CaptureQueriesContext(connection) as ctx:
        form.save(
            modeles=[modele],
            overwrite_strategy=GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
        )
    return len(ctx.captured_queries)


@pytest.mark.django_db
def test_generate_documents_create_form_save_is_not_n_plus_1_on_all_mentions():
    """Regression test: a modele using every possible mention must not add a
    query per projet. replace_mentions_in_html() and _log_doc_action() both
    walk the enveloppe_projet -> projet -> dossier_ds -> ds_demandeur/perimetre
    chain for every mention, so the batch must eager-load it once for the
    whole batch instead of once per projet."""
    modele = ModeleLettreNotificationFactory(
        dotation=DOTATION_DETR, content=_content_with_every_mention()
    )

    one = EnveloppeProjetFactory.create_batch(
        1, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    queries_for_one = _save_documents(one, modele)

    five = EnveloppeProjetFactory.create_batch(
        5, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    queries_for_five = _save_documents(five, modele)

    # The only per-projet query left should be the document INSERT itself
    # (one row per projet, GENERATE_DOCUMENT_SIZE=False in tests so no PDF
    # rendering): +4 queries for +4 projets. If any hop in the mention chain
    # weren't eager-loaded, this delta would grow with the batch size instead.
    assert queries_for_five - queries_for_one == 4

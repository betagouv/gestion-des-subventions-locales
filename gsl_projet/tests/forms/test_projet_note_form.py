import pytest
from django import forms
from django.db import IntegrityError, transaction

from gsl_core.tests.factories import CollegueFactory
from gsl_projet.forms import ProjetNoteForm
from gsl_projet.models import ProjetNote
from gsl_projet.tests.factories import (
    ProjetFactory,
)


@pytest.mark.django_db
def test_projet_note_form_fields():
    form = ProjetNoteForm()

    expected_fields = ["title", "content"]
    assert list(form.fields.keys()) == expected_fields

    title_field = form.fields["title"]
    assert isinstance(title_field, forms.CharField)
    assert title_field.required is True
    assert title_field.label == "Titre de la note"

    content_field = form.fields["content"]
    assert isinstance(content_field, forms.CharField)
    assert content_field.required is True
    assert content_field.label == "Note"
    assert content_field.widget.__class__ == forms.Textarea
    assert content_field.widget.attrs["rows"] == 6


@pytest.mark.django_db
def test_projet_note_form_validation():
    valid_data = {
        "title": "titre",
        "content": "contenu",
    }
    form = ProjetNoteForm(data=valid_data)
    assert form.is_valid()

    invalid_data = {
        "titre": "plusde255caracters" * 20,
        "content": "contenu",
    }
    form = ProjetNoteForm(data=invalid_data)
    assert not form.is_valid()
    assert "title" in form.errors


@pytest.mark.django_db
def test_dotation_projet_form_save():
    user = CollegueFactory()
    valid_data = {
        "title": "titre",
        "content": "contenu",
    }
    form = ProjetNoteForm(data=valid_data)
    assert form.is_valid()

    projet_note = form.save(commit=False)
    assert isinstance(projet_note, ProjetNote)

    with pytest.raises(IntegrityError):
        # Why this "with transaction.atomic():" ?
        # However, in Django 1.5/1.6, each test is wrapped in a transaction, so if an exception occurs,
        # it breaks the transaction until you explicitly roll it back.
        # Therefore, any further ORM operations in that transaction, such as my do_more_model_stuff(),
        # will fail with that django.db.transaction.TransactionManagementError exception.
        # https://stackoverflow.com/a/23326971/11207718
        with transaction.atomic():
            projet_note.save()

    projet_note.created_by = user

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            projet_note.save()

    projet_note.projet = ProjetFactory()
    projet_note.save()
    assert projet_note.title == "titre"
    assert projet_note.content == "contenu"
    assert projet_note.projet is not None
    assert projet_note.created_by is not None
    assert projet_note.created_at is not None
    assert projet_note.updated_at is not None

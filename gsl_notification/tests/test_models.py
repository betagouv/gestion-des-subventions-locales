from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from gsl_core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl_notification.models import ModeleArrete
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    LettreRefusFactory,
    LettreRefusSigneeFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
    ModeleLettreRefusFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ARRETE, DOTATION_DETR, DOTATION_DSIL, LETTRE


@pytest.mark.django_db
@pytest.mark.parametrize(
    "type, modele_factory, factory",
    (
        (ARRETE, ModeleArreteFactory, ArreteFactory),
        (
            LETTRE,
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
        ),
    ),
)
def generated_document_properties(type, modele_factory, factory):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    modele = modele_factory()

    file_content = {"key": "value"}
    arrete = factory(
        created_by=collegue,
        programmation_projet=programmation_projet,
        content=file_content,
        modele=modele,
    )

    if type == ARRETE:
        assert str(arrete) == f"Arrêté #{arrete.id}"
    else:
        assert str(arrete) == f"Lettre de notification #{arrete.id}"

    assert arrete.content == file_content
    assert arrete.created_by == collegue
    assert arrete.created_at is not None
    assert arrete.updated_at is not None
    assert arrete.programmation_projet == programmation_projet
    assert arrete.modele == modele


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modele_factory, factory",
    (
        (ModeleArreteFactory, ArreteFactory),
        (
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
        ),
    ),
)
def test_generated_document_save_calculates_size(modele_factory, factory):
    """Test that the save method calculates and saves the size field"""
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    modele = modele_factory()

    # Mock the logo base64 to avoid external requests
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = factory(
            programmation_projet=programmation_projet,
            content="<p>Test content</p>",
            modele=modele,
        )

    # Verify size is calculated and saved
    assert document.size is not None
    assert isinstance(document.size, int)
    assert document.size > 0
    # A minimal PDF should be at least 100 bytes
    assert document.size >= 100

    # Verify size is persisted in database
    document.refresh_from_db()
    assert document.size is not None
    assert document.size > 0


@override_settings(GENERATE_DOCUMENT_SIZE=True)
@patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "modele_factory, factory",
    (
        (ModeleArreteFactory, ArreteFactory),
        (
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
        ),
    ),
)
def test_generated_document_save_updates_size_on_content_change(
    mock_get_logo_base64, modele_factory, factory
):
    """Test that the save method recalculates size when content changes"""
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    modele = modele_factory()

    # Mock the logo base64 to avoid external requests - keep it active for both saves
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = factory(
            programmation_projet=programmation_projet,
            content="<p>Short content</p>",
            modele=modele,
        )

        initial_size = document.size
        assert initial_size is not None

        # Update content with longer content
        document.content = (
            "<p>This is a much longer content that should result in a larger PDF file size when generated</p>"
            * 10
        )
        document.save()

        # Verify size was recalculated
        assert document.size is not None
        assert document.size != initial_size
        # The new size should be different (likely larger due to more content)
        document.refresh_from_db()
        assert document.size != initial_size


@override_settings(GENERATE_DOCUMENT_SIZE=True)
@pytest.mark.django_db
@patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64")
@pytest.mark.parametrize(
    "modele_factory, factory",
    (
        (ModeleArreteFactory, ArreteFactory),
        (
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
        ),
    ),
)
def test_generated_document_save_with_different_content_sizes(
    mock_get_logo_base64, modele_factory, factory
):
    """Test that size calculation works correctly with different content sizes"""
    # Create separate programmation_projets since Arrete/LettreNotification have OneToOneField
    programmation_projet1 = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    programmation_projet2 = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    modele = modele_factory()

    # Mock the logo base64 to avoid external requests - keep it active for both document creations
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        # Create document with minimal content
        document1 = factory(
            programmation_projet=programmation_projet1,
            content="<p>Minimal</p>",
            modele=modele,
        )
        size1 = document1.size

        # Create another document with more content
        document2 = factory(
            programmation_projet=programmation_projet2,
            content="<p>" + "Long content " * 1000 + "</p>",
            modele=modele,
        )
        size2 = document2.size

        # Both should have valid sizes
        assert size1 is not None
        assert size2 is not None
        assert size1 > 0
        assert size2 > 0
        # Size2 should generally be larger than size1 (though PDF compression might affect this)
        # At minimum, both should be valid PDF sizes
        assert size1 >= 100
        assert size2 >= 100
        assert size2 > size1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modele_factory, factory",
    (
        (ModeleArreteFactory, ArreteFactory),
        (
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
        ),
    ),
)
def test_generate_document_validation_error_when_pp_and_model_have_different_dotation(
    modele_factory, factory
):
    pp = ProgrammationProjetFactory(dotation_projet__dotation=DOTATION_DSIL)
    modele = modele_factory(dotation=DOTATION_DETR)
    # Mock the logo base64 to avoid external requests during save()
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = factory(programmation_projet=pp, modele=modele)
    with pytest.raises(ValidationError) as exc_info:
        document.clean()

    assert exc_info.value.message == (
        "Le mod\xe8le doit avoir la m\xeame dotation que le projet de programmation."
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modele_factory, factory, message",
    (
        (
            ModeleArreteFactory,
            ArreteFactory,
            "Un arrêté ne peut être associé qu'à un projet de programmation accepté.",
        ),
        (
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
            "Une lettre de notification ne peut être associée qu'à un projet de "
            "programmation accepté.",
        ),
    ),
)
def test_generated_document_validation_error_when_pp_status_mismatch(
    modele_factory, factory, message
):
    pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_REFUSED)
    modele = modele_factory(dotation=pp.dotation)
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = factory(programmation_projet=pp, modele=modele)
    with pytest.raises(ValidationError) as exc_info:
        document.clean()

    assert exc_info.value.message == message


@pytest.mark.django_db
def test_lettre_refus_validation_error_when_pp_status_mismatch():
    pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_ACCEPTED)
    modele = ModeleLettreRefusFactory(dotation=pp.dotation)
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = LettreRefusFactory(programmation_projet=pp, modele=modele)
    with pytest.raises(ValidationError) as exc_info:
        document.clean()

    assert exc_info.value.message == (
        "Une lettre de refus ou de classement sans suite ne peut être associée "
        "qu'à un projet de programmation refusé ou classé sans suite."
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "modele_factory, factory",
    (
        (ModeleArreteFactory, ArreteFactory),
        (ModeleLettreNotificationFactory, LettreNotificationFactory),
    ),
)
def test_generated_document_no_error_when_pp_accepted(modele_factory, factory):
    pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_ACCEPTED)
    modele = modele_factory(dotation=pp.dotation)
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = factory(programmation_projet=pp, modele=modele)
    document.clean()  # should not raise


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    (ProgrammationProjet.STATUS_REFUSED, ProgrammationProjet.STATUS_DISMISSED),
)
def test_lettre_refus_no_error_when_pp_refused_or_dismissed(status):
    pp = ProgrammationProjetFactory(status=status)
    modele = ModeleLettreRefusFactory(dotation=pp.dotation)
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        document = LettreRefusFactory(programmation_projet=pp, modele=modele)
    document.clean()  # should not raise


@pytest.mark.parametrize("factory", (LettreEtArreteSignesFactory, AnnexeFactory))
@pytest.mark.django_db
def test_lettre_et_arrete_signes_properties(factory):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )

    file_content = b"dummy content"
    file = SimpleUploadedFile(
        "arrete/test_file.pdf", file_content, content_type="application/pdf"
    )

    doc = factory(
        file=file, created_by=collegue, programmation_projet=programmation_projet
    )

    if factory == LettreEtArreteSignesFactory:
        assert str(doc) == f"Lettre et arrêté signés #{doc.id}"
    else:
        assert str(doc) == f"Annexe #{doc.id}"

    assert doc.name.startswith(
        "test_file"
    )  # Filename can be changed with a suffix to avoid conflicts
    assert doc.file_type == "pdf"
    assert doc.size == len(file_content)
    assert doc.created_at is not None
    assert doc.created_by is collegue
    assert doc.programmation_projet == programmation_projet


@pytest.mark.parametrize(
    "factory", (ModeleArreteFactory, ModeleLettreNotificationFactory)
)
@pytest.mark.django_db
def test_modele_properties(factory):
    collegue = CollegueFactory()
    file_content = {"key": "value"}
    perimetre = collegue.perimetre
    modele = factory(created_by=collegue, content=file_content, perimetre=perimetre)

    assert str(modele) == modele.name

    assert modele.content == file_content
    assert modele.created_by == collegue
    assert modele.created_at is not None
    assert modele.updated_at is not None
    assert modele.perimetre == perimetre


@pytest.mark.django_db
def test_two_models_have_different_logos():
    updated_logo = SimpleUploadedFile("my_logo.png", b"logo content", "image/png")

    form_data = {
        "name": "Nom du modèle",
        "description": "Description du modèle",
        "perimetre": PerimetreDepartementalFactory(),
        "dotation": DOTATION_DETR,
        "logo": updated_logo,
        "logo_alt_text": "texte alternatif",
        "top_right_text": "Texte en haut à droite",
        "content": "<p>Contenu</p>",
        "created_by": CollegueFactory(),
    }

    first_modele = ModeleArrete(**form_data)
    first_modele.save()
    second_modele = ModeleArrete(**form_data)
    second_modele.save()

    assert first_modele.id != second_modele.id
    assert first_modele.name == second_modele.name
    assert first_modele.logo.name != second_modele.logo.name
    assert "my_logo" in first_modele.logo.name
    assert "my_logo" in second_modele.logo.name


@pytest.mark.django_db
def test_lettre_et_arrete_signes_validation_error_when_pp_status_mismatch():
    pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_REFUSED)
    doc = LettreEtArreteSignesFactory(programmation_projet=pp)
    with pytest.raises(ValidationError) as exc_info:
        doc.clean()

    assert exc_info.value.message == (
        "La lettre et l'arrêté signés ne peuvent être importés que pour un "
        "projet de programmation accepté."
    )


@pytest.mark.django_db
def test_lettre_refus_signee_validation_error_when_pp_status_mismatch():
    pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_ACCEPTED)
    doc = LettreRefusSigneeFactory(programmation_projet=pp)
    with pytest.raises(ValidationError) as exc_info:
        doc.clean()

    assert exc_info.value.message == (
        "La lettre de refus signée ne peut être importée que pour un projet "
        "de programmation refusé ou classé sans suite."
    )


@pytest.mark.parametrize(
    "status",
    (
        ProgrammationProjet.STATUS_ACCEPTED,
        ProgrammationProjet.STATUS_REFUSED,
        ProgrammationProjet.STATUS_DISMISSED,
    ),
)
@pytest.mark.django_db
def test_annexe_no_error_regardless_of_pp_status(status):
    pp = ProgrammationProjetFactory(status=status)
    doc = AnnexeFactory(programmation_projet=pp)
    doc.clean()  # should not raise


@pytest.mark.django_db
def test_lettre_et_arrete_signes_no_error_when_pp_accepted():
    pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_ACCEPTED)
    doc = LettreEtArreteSignesFactory(programmation_projet=pp)
    doc.clean()  # should not raise


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    (ProgrammationProjet.STATUS_REFUSED, ProgrammationProjet.STATUS_DISMISSED),
)
def test_lettre_refus_signee_no_error_when_pp_refused_or_dismissed(status):
    pp = ProgrammationProjetFactory(status=status)
    doc = LettreRefusSigneeFactory(programmation_projet=pp)
    doc.clean()  # should not raise

import datetime
import io
import os
from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from pikepdf import Pdf

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.tests.factories import PersonneMoraleFactory
from gsl_notification.models import (
    Annexe,
    ArreteEtLettreSignes,
)
from gsl_notification.tests.factories import AnnexeFactory
from gsl_notification.utils import (
    _get_uploaded_document_pdf,
    get_modele_perimetres,
    merge_documents_into_pdf,
    replace_mentions_in_html,
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory


@pytest.fixture
def programmation_projet():
    perimetre = PerimetreDepartementalFactory(
        departement__name="Haute-Garonne",
    )
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__ds_demandeur=PersonneMoraleFactory(
            raison_sociale="Commune de Bagnères-de-Luchon"
        ),
        dotation_projet__projet__dossier_ds__projet_intitule="Nouvelle plaque d'égoûts",
        dotation_projet__projet__perimetre=perimetre,
        dotation_projet__projet__dossier_ds__date_debut=datetime.date(1998, 7, 12),
        dotation_projet__projet__dossier_ds__date_achevement=datetime.date(2024, 7, 31),
        montant=2_000.50,
        dotation_projet__assiette=20_000,
    )


@pytest.mark.parametrize(
    "id, label, expected_value",
    (
        (1, "Nom du bénéficiaire", "Commune de Bagnères-de-Luchon"),
        (2, "Intitulé du projet", "Nouvelle plaque d'égoûts"),
        (3, "Nom du département", "Haute-Garonne"),
        (4, "Montant prévisionnel de la subvention", "2 000,50 €"),
        (5, "Taux de subvention", "10,002 %"),
        (6, "Date de commencement", "12/07/1998"),
        (7, "Date d'achèvement", "31/07/2024"),
    ),
)
@pytest.mark.django_db
def test_replace_mentions_in_html(id, label, expected_value, programmation_projet):
    html_content = f'<p>Voici le mot: <span class="mention" data-type="mention" data-id="{id}" data-label="{label}" data-mention-suggestion-char="@">@{label}</span> vous octroie une subvention</p><p>Bravo et merci !</p>'
    expected_text = f"<p>Voici le mot: {expected_value} vous octroie une subvention</p><p>Bravo et merci !</p>"

    assert expected_text == replace_mentions_in_html(html_content, programmation_projet)


def test_update_file_name_to_put_it_in_a_programmation_projet_folder():
    # Simulate a file-like object with a 'name' attribute
    class DummyFile(io.BytesIO):
        def __init__(self, name):
            super().__init__()
            self.name = name

    file = DummyFile("document.pdf")
    programmation_projet_id = 42

    update_file_name_to_put_it_in_a_programmation_projet_folder(
        file, programmation_projet_id
    )

    assert file.name == "programmation_projet_42/document.pdf"


@pytest.mark.django_db
def test_update_file_name_to_put_it_in_a_programmation_projet_folder_with_annexe():
    pp = ProgrammationProjetFactory()
    annexe = AnnexeFactory(programmation_projet=pp)
    assert pp.annexes.count() == 1

    class DummyFile(io.BytesIO):
        def __init__(self, name):
            super().__init__()
            self.name = name

    file_name = annexe.name
    base_name, _extension = os.path.splitext(file_name)
    file_2 = DummyFile(file_name)

    update_file_name_to_put_it_in_a_programmation_projet_folder(
        file_2, pp.id, is_annexe=True
    )

    assert file_2.name == f"programmation_projet_{pp.id}/{base_name}_2.pdf"


@pytest.mark.django_db
def test_get_modele_perimetres():
    arrondissement_11 = PerimetreArrondissementFactory()
    departement_1 = PerimetreDepartementalFactory(
        departement=arrondissement_11.departement, region=arrondissement_11.region
    )
    region = PerimetreRegionalFactory(region=departement_1.region)
    arrondissement_12 = PerimetreArrondissementFactory(
        arrondissement__departement=departement_1.departement,
        departement=departement_1.departement,
        region=region.region,
    )

    departement_2 = PerimetreDepartementalFactory(
        departement__region=region.region, region=region.region
    )
    _arrondissement_21 = PerimetreArrondissementFactory(
        arrondissement__departement=departement_2.departement,
        region=region.region,
        departement=departement_2.departement,
    )

    assert get_modele_perimetres("DETR", arrondissement_11) == [
        arrondissement_11,
        departement_1,
    ]
    assert get_modele_perimetres("DETR", departement_1) == [departement_1]
    with pytest.raises(ValueError) as exc_info:
        assert get_modele_perimetres("DETR", region) == [region]
    assert str(exc_info.value) == (
        "Les modèles de la dotation DETR ne sont pas accessibles pour les utilisateurs dont le périmètre n'est pas de type arrondissement ou départemental."
    )

    assert get_modele_perimetres("DSIL", arrondissement_12) == [
        arrondissement_12,
        departement_1,
        region,
    ]
    assert get_modele_perimetres("DSIL", departement_1) == [departement_1, region]
    assert get_modele_perimetres("DSIL", region) == [region]


class TestMergeDocumentsIntoPdf:
    """Tests for the merge_documents_into_pdf function."""

    @pytest.fixture
    def sample_pdf_bytes(self):
        """Create a simple PDF in bytes format."""
        pdf = Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))  # Letter size
        bytes_io = io.BytesIO()
        pdf.save(bytes_io)
        bytes_io.seek(0)
        return bytes_io

    @pytest.fixture
    def sample_two_page_pdf_bytes(self):
        """Create a two-page PDF in bytes format."""
        pdf = Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        pdf.add_blank_page(page_size=(612, 792))
        bytes_io = io.BytesIO()
        pdf.save(bytes_io)
        bytes_io.seek(0)
        return bytes_io

    @pytest.fixture
    def sample_image_bytes(self):
        """Create a simple image in bytes format (1x1 pixel PNG)."""
        # Minimal valid PNG file (1x1 white pixel)
        return (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\x0d"  # IHDR chunk length
            b"IHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"  # width=1, height=1
            b"\x08\x06\x00\x00\x00"  # bit depth=8, color type=6 (RGBA), compression=0, filter=0
            b"\x1f\x15\xc4\x89"  # IHDR CRC
            b"\x00\x00\x00\x0a"  # IDAT chunk length
            b"IDAT"
            b"\x78\x9c\x63\x00\x01\x00\x00\x05\x00\x01"  # minimal IDAT
            b"\x0d\x0a\x2d\xb4"  # IDAT CRC
            b"\x00\x00\x00\x00"  # IEND chunk length
            b"IEND"
            b"\xae\x42\x60\x82"  # IEND CRC
        )

    @pytest.fixture
    def mock_annexe(self):
        """Create a mock Annexe (UploadedDocument)."""
        annexe = Mock(spec=Annexe)
        annexe.__class__ = Annexe
        annexe.file.name = "test_annexe.pdf"
        return annexe

    @pytest.fixture
    def mock_arrete_signe(self):
        """Create a mock ArreteEtLettreSignes (UploadedDocument)."""
        arrete_signe = Mock(spec=ArreteEtLettreSignes)
        arrete_signe.__class__ = ArreteEtLettreSignes
        arrete_signe.file.name = "test_arrete_signe.pdf"
        return arrete_signe

    @patch("gsl_notification.utils.get_s3_object")
    def test_merge_single_uploaded_pdf_document(
        self, mock_get_s3, mock_annexe, sample_pdf_bytes
    ):
        """Test merging a single uploaded PDF document."""
        mock_s3_response = {
            "Body": Mock(read=Mock(return_value=sample_pdf_bytes)),
            "ContentType": "application/pdf",
        }
        mock_get_s3.return_value = mock_s3_response

        result = merge_documents_into_pdf([mock_annexe])

        assert isinstance(result, SimpleUploadedFile)
        assert result.name == "documents.pdf"
        assert result.content_type == "application/pdf"

        # Verify the result is a valid PDF
        pdf = Pdf.open(io.BytesIO(result.read()))
        assert len(pdf.pages) == 1
        mock_get_s3.assert_called_once_with("test_annexe.pdf")

    @patch("gsl_notification.utils.get_s3_object")
    def test_uploaded_document_img2pdf_conversion(
        self,
        mock_get_s3,
        mock_annexe,
        sample_image_bytes,
        sample_pdf_bytes,
    ):
        """Test merging a single uploaded image document (converts to PDF)."""
        mock_s3_response = {
            "Body": Mock(read=Mock(return_value=sample_image_bytes)),
            "ContentType": "image/png",
        }
        mock_get_s3.return_value = mock_s3_response

        bytes = _get_uploaded_document_pdf(mock_annexe)

        # Verify the result is a valid PDF
        pdf = Pdf.open(bytes)
        assert len(pdf.pages) == 1

    @patch("gsl_notification.utils.get_s3_object")
    def test_merge_multiple_uploaded_documents(
        self,
        mock_get_s3,
        mock_annexe,
        mock_arrete_signe,
        sample_pdf_bytes,
        sample_two_page_pdf_bytes,
    ):
        """Test merging multiple uploaded documents."""
        mock_get_s3.side_effect = [
            {
                "Body": Mock(read=Mock(return_value=sample_pdf_bytes)),
                "ContentType": "application/pdf",
            },
            {
                "Body": Mock(read=Mock(return_value=sample_two_page_pdf_bytes)),
                "ContentType": "application/pdf",
            },
        ]

        result = merge_documents_into_pdf([mock_annexe, mock_arrete_signe])

        assert isinstance(result, SimpleUploadedFile)

        # Verify the merged PDF has all pages (1 + 2 = 3)
        pdf = Pdf.open(io.BytesIO(result.read()))
        assert len(pdf.pages) == 3
        assert mock_get_s3.call_count == 2

    def test_merge_empty_list(self):
        """Test merging an empty list of documents."""
        result = merge_documents_into_pdf([])

        assert isinstance(result, SimpleUploadedFile)
        assert result.name == "documents.pdf"
        assert result.content_type == "application/pdf"

        # Verify the result is a valid PDF with no pages
        pdf = Pdf.open(io.BytesIO(result.read()))
        assert len(pdf.pages) == 0

    @patch("gsl_notification.utils.get_s3_object")
    def test_result_is_seeked_to_beginning(
        self, mock_get_s3, mock_arrete_signe, sample_pdf_bytes
    ):
        """Test merging a single uploaded PDF document."""
        mock_s3_response = {
            "Body": Mock(read=Mock(return_value=sample_pdf_bytes)),
            "ContentType": "application/pdf",
        }
        mock_get_s3.return_value = mock_s3_response

        result = merge_documents_into_pdf([mock_arrete_signe])

        # The file should be readable from the beginning
        content = result.read()
        assert len(content) > 0
        assert content[:4] == b"%PDF"  # PDF magic number

    @patch("gsl_notification.utils.get_s3_object")
    def test_uploaded_document_fetching_called_correctly(
        self, mock_get_s3, mock_annexe, sample_pdf_bytes
    ):
        """Test that uploaded documents are fetched from S3 correctly."""
        mock_s3_response = {
            "Body": Mock(read=Mock(return_value=sample_pdf_bytes)),
            "ContentType": "application/pdf",
        }
        mock_get_s3.return_value = mock_s3_response

        merge_documents_into_pdf([mock_annexe])

        # Verify S3 was called with correct file name
        mock_get_s3.assert_called_once_with("test_annexe.pdf")

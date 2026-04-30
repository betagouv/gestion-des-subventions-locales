import io
import zipfile
from datetime import UTC, datetime
from html import unescape
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.tests.factories import (
    LettreNotificationFactory,
    ModeleLettreNotificationFactory,
)
from gsl_notification.utils import generate_pdf_for_generated_document
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, LETTRE

pytestmark = pytest.mark.django_db


## FIXTURES


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def programmation_projet(perimetre):
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre
    )


@pytest.fixture
def programmation_projets(perimetre):
    return ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )


@pytest.fixture
def detr_lettre_modele(perimetre):
    return ModeleLettreNotificationFactory(dotation=DOTATION_DETR, perimetre=perimetre)


@pytest.fixture
def client(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


## download_documents


def test_download_documents_method_allowed(client):
    url = reverse(
        "notification:download-documents",
        kwargs={
            "dotation": DOTATION_DETR,
            "document_type": LETTRE,
        },
    )
    assert url == f"/notification/{DOTATION_DETR}/telechargement/lettre"
    response = client.post(url)
    assert response.status_code == 405


@override_settings(DEBUG=False)
def test_download_documents_with_wrong_dotation(client):
    url = reverse("notification:download-documents", args=["raté", LETTRE])
    response = client.get(url)
    assert response.status_code == 404
    assert "Dotation inconnue" in unescape(response.content.decode("utf-8"))


@override_settings(DEBUG=False)
def test_download_documents_with_wrong_document_type(client):
    url = reverse(
        "notification:download-documents",
        args=[DOTATION_DETR, "raté"],
    )
    response = client.get(url)
    assert response.status_code == 404
    assert "Type de document inconnu" in unescape(response.content.decode("utf-8"))


def test_download_documents_no_id(client):
    pps = []
    # Must be selected (good perimetre, status and notified_at)
    pps += ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__dotation=DOTATION_DETR,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    # Must not be selected
    pps += ProgrammationProjetFactory.create_batch(
        5,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    pps += ProgrammationProjetFactory.create_batch(
        4,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=datetime.now(UTC),
    )

    for pp in pps:
        LettreNotificationFactory(programmation_projet=pp)

    url = reverse(
        "notification:download-documents",
        args=[DOTATION_DETR, LETTRE],
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="documents.zip"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 3


def test_download_documents_no_id_with_filters(client):
    data = {"montant_demande_min": "100000"}

    pps = []
    for amount in [50_000, 100_000, 150_000]:
        pps.append(
            ProgrammationProjetFactory(
                dotation_projet__dotation=DOTATION_DETR,
                dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
                dotation_projet__projet__dossier_ds__demande_montant=amount,
                status=ProgrammationProjet.STATUS_ACCEPTED,
                notified_at=None,
            )
        )

    for pp in pps:
        LettreNotificationFactory(programmation_projet=pp)

    url = reverse(
        "notification:download-documents",
        args=[DOTATION_DETR, LETTRE],
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        response = client.get(url, data)

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="documents.zip"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 2


def test_download_documents_with_one_wrong_perimetre_pp(client, programmation_projets):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR
    )
    programmation_projets.append(wrong_perimetre_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 403
    # Check that the custom user message appears in the response
    assert (
        "Un ou plusieurs projets sont hors de votre périmètre."
        in response.content.decode("utf-8")
    )


def test_download_documents_with_one_wrong_dotation_pp(client, programmation_projets):
    wrong_dotation_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DSIL
    )
    programmation_projets.append(wrong_dotation_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_one_already_notified(client, programmation_projets):
    already_notified_pp = ProgrammationProjetFactory(notified_at=datetime.now(UTC))
    programmation_projets.append(already_notified_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_one_refused(client, programmation_projets):
    refuse_pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_REFUSED)
    programmation_projets.append(refuse_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_missing_doc(client, programmation_projets):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)
    pp_without_lettre = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DSIL
    )
    programmation_projets.append(pp_without_lettre)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_duplicate_id(client, programmation_projets):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    ids += f",{str(programmation_projets[0].id)}"
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_correctly(client, programmation_projets):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)
    pp_ids = [str(pp.id) for pp in programmation_projets]
    ids = ",".join(pp_ids)
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="documents.zip"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 3


def test_download_documents_single_doc_returns_pdf(client):
    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    LettreNotificationFactory(programmation_projet=pp)
    url = (
        reverse("notification:download-documents", args=[DOTATION_DETR, LETTRE])
        + f"?ids={pp.id}"
    )
    with patch("gsl_notification.utils.get_logo_base64", return_value="mocked_base64"):
        response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


## Modal HTMX views

HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}


## GenerateDocumentsModalView


def test_generate_documents_modal_requires_htmx(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse("gsl_notification:generate-documents-modal", args=[DOTATION_DETR])
    response = client.post(url, {"ids": ids})
    assert response.status_code == 400


@override_settings(DEBUG=False)
def test_generate_documents_modal_wrong_dotation(client):
    url = reverse("gsl_notification:generate-documents-modal", args=["raté"])
    response = client.post(url, {}, **HTMX_HEADERS)
    assert response.status_code == 404
    assert "Dotation inconnue" in unescape(response.content.decode("utf-8"))


def test_generate_documents_modal_with_ids(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse("gsl_notification:generate-documents-modal", args=[DOTATION_DETR])
    response = client.post(url, {"ids": ids}, **HTMX_HEADERS)
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple/modal_step1.html"
    )
    assert response.context["pp_count"] == 3


def test_generate_documents_modal_without_ids_uses_filter(client):
    ProgrammationProjetFactory.create_batch(
        2,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    url = reverse("gsl_notification:generate-documents-modal", args=[DOTATION_DETR])
    response = client.post(url, {}, **HTMX_HEADERS)
    assert response.status_code == 200
    assert response.context["pp_count"] == 2


## GenerateDocumentsModalStep2View


def test_generate_documents_modal_step2_requires_htmx(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-step2", args=[DOTATION_DETR]
    )
    response = client.post(url, {"document_type": LETTRE, "ids": ids})
    assert response.status_code == 400


@override_settings(DEBUG=False)
def test_generate_documents_modal_step2_wrong_document_type(
    client, programmation_projets
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-step2", args=[DOTATION_DETR]
    )
    response = client.post(url, {"document_type": "raté", "ids": ids}, **HTMX_HEADERS)
    assert response.status_code == 404
    assert "Type de document inconnu" in unescape(response.content.decode("utf-8"))


def test_generate_documents_modal_step2_returns_modeles(
    client, programmation_projets, detr_lettre_modele
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-step2", args=[DOTATION_DETR]
    )
    response = client.post(url, {"document_type": LETTRE, "ids": ids}, **HTMX_HEADERS)
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple/modal_step2_body.html"
    )
    assert detr_lettre_modele in response.context["modeles"]
    assert response.context["document_type"] == LETTRE
    assert response.context["ids"] == ids


## GenerateDocumentsModalLoadingView


def test_generate_documents_modal_loading_missing_modele_returns_step2_with_error(
    client, programmation_projets
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-loading", args=[DOTATION_DETR]
    )
    response = client.post(
        url, {"document_type": LETTRE, "ids": ids, "modele_id": ""}, **HTMX_HEADERS
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple/modal_step2_body.html"
    )
    assert response.context["error"] == "Veuillez sélectionner un modèle."


def test_generate_documents_modal_loading_valid(
    client, programmation_projets, detr_lettre_modele
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-loading", args=[DOTATION_DETR]
    )
    response = client.post(
        url,
        {"document_type": LETTRE, "ids": ids, "modele_id": str(detr_lettre_modele.id)},
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple/modal_loading_body.html"
    )
    assert response.context["pp_count"] == 3
    assert response.context["modele_id"] == str(detr_lettre_modele.id)


## GenerateDocumentsModalCreateView


def test_generate_documents_modal_create_requires_htmx(
    client, programmation_projets, detr_lettre_modele
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-create", args=[DOTATION_DETR]
    )
    response = client.post(
        url,
        {"document_type": LETTRE, "ids": ids, "modele_id": str(detr_lettre_modele.id)},
    )
    assert response.status_code == 400


@override_settings(DEBUG=False)
def test_generate_documents_modal_create_wrong_dotation(client):
    url = reverse("gsl_notification:generate-documents-modal-create", args=["raté"])
    response = client.post(url, {}, **HTMX_HEADERS)
    assert response.status_code == 404


def test_generate_documents_modal_create_creates_documents_and_returns_success(
    client, programmation_projets, detr_lettre_modele
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-create", args=[DOTATION_DETR]
    )
    response = client.post(
        url,
        {"document_type": LETTRE, "ids": ids, "modele_id": str(detr_lettre_modele.id)},
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple/modal_success_body.html"
    )
    assert response.context["doc_count"] == 3
    assert response.context["doc_name"] == "lettres de notification"
    for pp in programmation_projets:
        pp.refresh_from_db()
        assert hasattr(pp, "lettre_notification")
        assert pp.lettre_notification.modele == detr_lettre_modele
        assert pp.lettre_notification.created_by == client.user


def test_generate_documents_modal_create_replaces_existing_doc(
    client, programmation_projets, detr_lettre_modele
):
    pp = programmation_projets[0]
    old_lettre = LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = reverse(
        "gsl_notification:generate-documents-modal-create", args=[DOTATION_DETR]
    )
    client.post(
        url,
        {"document_type": LETTRE, "ids": ids, "modele_id": str(detr_lettre_modele.id)},
        **HTMX_HEADERS,
    )
    pp.refresh_from_db()
    assert pp.lettre_notification.id != old_lettre.id


def test_generate_pdf_for_document_unit(detr_lettre_modele, programmation_projet):
    document = LettreNotificationFactory(
        programmation_projet=programmation_projet,
        modele=detr_lettre_modele,
        content="<p>Test PDF</p>",
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        pdf_bytes = generate_pdf_for_generated_document(document)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 100

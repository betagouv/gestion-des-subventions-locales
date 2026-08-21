import io
import os
import zipfile
from html import unescape
from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils.text import slugify
from freezegun import freeze_time

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.forms import (
    ARRETE_ET_LETTRE,
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_DOC,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    GenerateDocumentsModeleSelectionForm,
)
from gsl_notification.models import LettreNotification
from gsl_notification.tests.factories import (
    LettreNotificationFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, LETTRE

pytestmark = pytest.mark.django_db


## FIXTURES


@pytest.fixture
def perimetre():
    return PerimetreFactory()


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
def detr_arrete_modele(perimetre):
    return ModeleArreteFactory(dotation=DOTATION_DETR, perimetre=perimetre)


@pytest.fixture
def client(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture(autouse=True)
def _mock_logo_base64():
    """The create step of the wizard renders every PDF synchronously, which
    fetches the modele logo via HTTP. Mock it so tests don't hit the network."""
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        yield


## Helpers


HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}

WIZARD_PREFIX_DETR = f"generate_accepted_documents_wizard_{DOTATION_DETR}"


def _wizard_url(dotation=DOTATION_DETR):
    from django.urls import reverse

    return reverse("gsl_notification:generate-documents-modal", args=[dotation])


def _status_url(dotation, job_id):
    from django.urls import reverse

    return reverse(
        "gsl_notification:generate-documents-status",
        kwargs={"dotation": dotation, "job_id": job_id},
    )


def _wizard_step_data(current_step, fields, prefix=WIZARD_PREFIX_DETR):
    """Build POST data for a wizard step submission, with management form."""
    data = {f"{prefix}-current_step": current_step}
    for key, value in fields.items():
        data[f"{current_step}-{key}"] = value
    return data


def _post_launch(client, ids=None, dotation=DOTATION_DETR):
    """POST the launch step of the wizard (the entry triggered by the button)."""
    fields = {}
    if ids is not None:
        fields["ids"] = ids
    return client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "launch", fields, prefix=f"generate_accepted_documents_wizard_{dotation}"
        ),
        **HTMX_HEADERS,
    )


def _storage_key_from_url(url):
    """InMemoryStorage returns '/media/<key>' — strip the media prefix.
    The url is URL-encoded; decode it back to the on-disk key."""
    from urllib.parse import unquote

    return unquote(url.removeprefix("/media/"))


def _read_storage_body(url):
    key = _storage_key_from_url(url)
    assert default_storage.exists(key)
    with default_storage.open(key) as f:
        return key, f.read()


def _template_names(response):
    # The create step renders PDFs via render_to_string before rendering the success
    # template, so the success template is not always at index 0. Compare
    # against the full set.
    return {t.name for t in response.templates}


## Launch step (PRG entry) and wizard GET (dialog rendering)


def test_launch_requires_htmx(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    response = client.post(
        _wizard_url(),
        _wizard_step_data("launch", {"ids": ids}),
    )
    assert response.status_code == 400


@override_settings(DEBUG=False)
def test_wizard_wrong_dotation(client):
    response = client.get(_wizard_url("raté"), **HTMX_HEADERS)
    assert response.status_code == 404
    assert "Dotation inconnue" in unescape(response.content.decode("utf-8"))


def test_launch_with_valid_ids_renders_type_selection_step_dialog(
    client, programmation_projets
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    response = _post_launch(client, ids=ids)
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_form_step.html"
    )
    assert "HX-Location" not in response.headers


def test_launch_no_projects_renders_error_body(client):
    response = _post_launch(client, ids="")
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_launch.html"
    )
    form = response.context["form"]
    assert "Aucun projet à notifier." in " ".join(form.errors.get("ids", []))
    assert "HX-Location" not in response.headers


def test_launch_wrong_perimetre_renders_error_body(client):
    wrong_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    response = _post_launch(client, ids=str(wrong_pp.id))
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_launch.html"
    )
    form = response.context["form"]
    assert "choix valide" in " ".join(form.errors.get("ids", []))


## Wizard step submissions


def _open_wizard_at_type_selection_step(client, programmation_projets):
    """POST the launch step so the type_selection step (doc_type) is initialized."""
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    _post_launch(client, ids=ids)
    return ids


def test_wizard_type_selection_invalid_document_type_re_renders_type_selection(
    client, programmation_projets
):
    _open_wizard_at_type_selection_step(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": "raté"}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_form_step.html"
    )
    form = response.context["form"]
    assert "Type de document inconnu" in " ".join(form["document_type"].errors)


def test_wizard_type_selection_to_modele_selection_renders_modeles(
    client, programmation_projets, detr_lettre_modele
):
    _open_wizard_at_type_selection_step(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": LETTRE}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_modele_selection.html"
    )
    form = response.context["form"]
    assert detr_lettre_modele in form.fields["modele_lettre_id"].queryset
    assert form.document_type == LETTRE


def test_wizard_type_selection_to_modele_selection_both_types_renders_two_selectors(
    client, programmation_projets, detr_arrete_modele, detr_lettre_modele
):
    _open_wizard_at_type_selection_step(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": ARRETE_ET_LETTRE}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_modele_selection.html"
    )
    form = response.context["form"]
    assert detr_arrete_modele in form.fields["modele_arrete_id"].queryset
    assert detr_lettre_modele in form.fields["modele_lettre_id"].queryset
    assert form.document_type == ARRETE_ET_LETTRE


def test_wizard_modele_selection_field_order_matches_figma(
    client, programmation_projets, detr_arrete_modele, detr_lettre_modele
):
    """Figma: Conserver/Remplacer first, then lettres, then arrêtés."""
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    _open_wizard_at_type_selection_step(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": ARRETE_ET_LETTRE}),
        **HTMX_HEADERS,
    )
    form = response.context["form"]
    assert list(form.fields) == [
        "overwrite_strategy",
        "modele_lettre_id",
        "modele_arrete_id",
    ]


def test_wizard_modele_selection_missing_modele_re_renders_modele_selection(
    client, programmation_projets
):
    """Regression: previously the format view rendered modele_selection on missing_modele."""
    _open_wizard_at_type_selection_step(client, programmation_projets)
    client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": LETTRE}),
        **HTMX_HEADERS,
    )
    response = client.post(
        _wizard_url(),
        _wizard_step_data("modele_selection", {"modele_lettre_id": ""}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_modele_selection.html"
    )
    form = response.context["form"]
    assert form.errors["modele_lettre_id"] == ["Veuillez sélectionner un modèle."]


def test_wizard_modele_selection_missing_both_modeles_re_renders_modele_selection(
    client, programmation_projets
):
    _open_wizard_at_type_selection_step(client, programmation_projets)
    client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": ARRETE_ET_LETTRE}),
        **HTMX_HEADERS,
    )
    response = client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection", {"modele_arrete_id": "", "modele_lettre_id": ""}
        ),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_modele_selection.html"
    )
    form = response.context["form"]
    assert form.errors["modele_arrete_id"] == ["Veuillez sélectionner un modèle."]
    assert form.errors["modele_lettre_id"] == ["Veuillez sélectionner un modèle."]


def test_wizard_modele_selection_to_format_step(
    client, programmation_projets, detr_lettre_modele
):
    _open_wizard_at_type_selection_step(client, programmation_projets)
    client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": LETTRE}),
        **HTMX_HEADERS,
    )
    response = client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection", {"modele_lettre_id": str(detr_lettre_modele.id)}
        ),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_form_step.html"
    )


def test_wizard_format_step_invalid_export_format_re_renders_format_step(
    client, programmation_projets, detr_lettre_modele
):
    """Regression: previously the loading view rendered the format step on invalid export_format."""
    _open_wizard_at_type_selection_step(client, programmation_projets)
    client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": LETTRE}),
        **HTMX_HEADERS,
    )
    client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection", {"modele_lettre_id": str(detr_lettre_modele.id)}
        ),
        **HTMX_HEADERS,
    )
    response = client.post(
        _wizard_url(),
        _wizard_step_data("format", {"export_format": ""}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_form_step.html"
    )
    form = response.context["form"]
    assert "Veuillez sélectionner un format d'export." in " ".join(
        form["export_format"].errors
    )


## Create step — final wizard step (loading body + auto-submit → done)


def _drive_through_format_step(
    client,
    programmation_projets,
    *,
    document_type=LETTRE,
    modele_selection_fields,
    export_format=EXPORT_FORMAT_ONE_PDF_PER_DOC,
    dotation=DOTATION_DETR,
):
    """Walk the wizard from launch through a format-step submit.

    Returns the response of the format POST (= initial create-step render).
    """
    _open_wizard_at_type_selection_step(client, programmation_projets)
    client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "type_selection",
            {"document_type": document_type},
            prefix=f"generate_accepted_documents_wizard_{dotation}",
        ),
        **HTMX_HEADERS,
    )
    client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "modele_selection",
            modele_selection_fields,
            prefix=f"generate_accepted_documents_wizard_{dotation}",
        ),
        **HTMX_HEADERS,
    )
    return client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "format",
            {"export_format": export_format},
            prefix=f"generate_accepted_documents_wizard_{dotation}",
        ),
        **HTMX_HEADERS,
    )


def _post_create_step_raw(client, dotation=DOTATION_DETR):
    """POST the create step and return the intermediate polling response."""
    return client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "create", {}, prefix=f"generate_accepted_documents_wizard_{dotation}"
        ),
        **HTMX_HEADERS,
    )


def _post_create_step(client, dotation=DOTATION_DETR):
    """POST the create step then poll the status endpoint; returns the final success response."""
    polling_response = _post_create_step_raw(client, dotation)
    job_id = polling_response.context["job_id"]
    return client.get(_status_url(dotation, job_id), **HTMX_HEADERS)


def test_wizard_format_step_renders_loading_body(
    client, programmation_projets, detr_lettre_modele
):
    response = _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={"modele_lettre_id": str(detr_lettre_modele.id)},
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_loading.html"
    )
    assert response.context["doc_count"] == 3
    # Loading body must include the wizard management form so the auto-POST
    # is dispatched to the wizard's create step.
    assert b"generate_accepted_documents_wizard_DETR-current_step" in response.content
    assert b'value="create"' in response.content


def test_wizard_create_step_returns_polling_template(
    client, programmation_projets, detr_lettre_modele
):
    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={"modele_lettre_id": str(detr_lettre_modele.id)},
    )
    response = _post_create_step_raw(client)
    assert response.status_code == 200
    assert (
        "gsl_notification/generated_document/multiple_wizard/modal_export_progress.html"
        in _template_names(response)
    )
    assert "job_id" in response.context
    assert "job" in response.context


def test_wizard_create_step_creates_documents_and_returns_success(
    client, programmation_projets, detr_lettre_modele
):
    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={"modele_lettre_id": str(detr_lettre_modele.id)},
    )
    response = _post_create_step(client)
    assert response.status_code == 200
    assert (
        "gsl_notification/generated_document/multiple_wizard/modal_success.html"
        in _template_names(response)
    )
    assert response.context["doc_count"] == 3
    assert len(list(response.context["refreshed_programmation_projets"])) == 3
    for pp in programmation_projets:
        pp.refresh_from_db()
        assert hasattr(pp, "lettre")
        assert pp.lettre.modele == detr_lettre_modele
        assert pp.lettre.created_by == client.user

    _, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"  # ZIP (3 docs)


def test_wizard_create_step_replaces_existing_doc(
    client, programmation_projets, detr_lettre_modele
):
    pp = programmation_projets[0]
    old_lettre = LettreNotificationFactory(programmation_projet=pp)

    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={
            "modele_lettre_id": str(detr_lettre_modele.id),
            "overwrite_strategy": GenerateDocumentsModeleSelectionForm.STRATEGY_REMPLACER,
        },
    )
    response = _post_create_step(client)
    pp.refresh_from_db()
    assert pp.lettre.id != old_lettre.id

    _, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"


def test_wizard_modele_selection_conserver_when_all_covered_advances_to_format_step(
    client, programmation_projets, detr_lettre_modele
):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    _open_wizard_at_type_selection_step(client, programmation_projets)
    client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": LETTRE}),
        **HTMX_HEADERS,
    )
    response = client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection",
            {
                "modele_lettre_id": str(detr_lettre_modele.id),
                "overwrite_strategy": GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
            },
        ),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == (
        "gsl_notification/generated_document/multiple_wizard/modal_form_step.html"
    )
    form = response.context["form"]
    assert "overwrite_strategy" not in form.errors
    # No new lettre created yet: only the original 3 fixtures remain.
    assert LettreNotification.objects.count() == 3


def test_wizard_create_step_conserver_creates_only_missing_documents(
    client, programmation_projets, detr_lettre_modele
):
    pp_with_existing, *pps_without = programmation_projets
    old_lettre = LettreNotificationFactory(programmation_projet=pp_with_existing)

    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={
            "modele_lettre_id": str(detr_lettre_modele.id),
            "overwrite_strategy": GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
        },
    )
    response = _post_create_step(client)
    assert response.status_code == 200
    assert (
        "gsl_notification/generated_document/multiple_wizard/modal_success.html"
        in _template_names(response)
    )

    pp_with_existing.refresh_from_db()
    assert pp_with_existing.lettre.id == old_lettre.id
    for pp in pps_without:
        pp.refresh_from_db()
        assert hasattr(pp, "lettre")
        assert pp.lettre.modele == detr_lettre_modele

    _, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"


def test_wizard_create_step_remplacer_when_all_covered_replaces_all(
    client, programmation_projets, detr_lettre_modele
):
    old_ids = []
    for pp in programmation_projets:
        old_ids.append(LettreNotificationFactory(programmation_projet=pp).id)

    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={
            "modele_lettre_id": str(detr_lettre_modele.id),
            "overwrite_strategy": GenerateDocumentsModeleSelectionForm.STRATEGY_REMPLACER,
        },
    )
    response = _post_create_step(client)
    assert response.status_code == 200
    assert (
        "gsl_notification/generated_document/multiple_wizard/modal_success.html"
        in _template_names(response)
    )
    for pp, old_id in zip(programmation_projets, old_ids, strict=True):
        pp.refresh_from_db()
        assert pp.lettre.id != old_id
        assert pp.lettre.modele == detr_lettre_modele

    _, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"


def test_wizard_create_step_conserver_full_coverage_with_empty_ids_reaches_success(
    client, programmation_projets, detr_lettre_modele
):
    """When the user selects all projets, the trigger form posts ids="" and the
    launch form's fallback resolves projets from the filterset. The wizard must
    still reach the create step's success when CONSERVER is chosen and every projet is
    already covered."""
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    _post_launch(client, ids="")
    client.post(
        _wizard_url(),
        _wizard_step_data("type_selection", {"document_type": LETTRE}),
        **HTMX_HEADERS,
    )
    client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection",
            {
                "modele_lettre_id": str(detr_lettre_modele.id),
                "overwrite_strategy": GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
            },
        ),
        **HTMX_HEADERS,
    )
    client.post(
        _wizard_url(),
        _wizard_step_data("format", {"export_format": EXPORT_FORMAT_ONE_PDF_PER_DOC}),
        **HTMX_HEADERS,
    )
    response = _post_create_step(client)
    assert response.status_code == 200
    assert (
        "gsl_notification/generated_document/multiple_wizard/modal_success.html"
        in _template_names(response)
    )
    assert LettreNotification.objects.count() == 3

    _, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"


def test_wizard_create_step_both_creates_arrete_and_lettre(
    client, programmation_projets, detr_arrete_modele, detr_lettre_modele
):
    _drive_through_format_step(
        client,
        programmation_projets,
        document_type=ARRETE_ET_LETTRE,
        modele_selection_fields={
            "modele_arrete_id": str(detr_arrete_modele.id),
            "modele_lettre_id": str(detr_lettre_modele.id),
        },
    )
    response = _post_create_step(client)
    assert response.status_code == 200
    assert (
        "gsl_notification/generated_document/multiple_wizard/modal_success.html"
        in _template_names(response)
    )
    assert response.context["doc_count"] == 6  # 3 projets × 2 types = ARRETE_ET_LETTRE
    assert "download_url" in response.context
    assert len(list(response.context["refreshed_programmation_projets"])) == 3
    for pp in programmation_projets:
        pp.refresh_from_db()
        assert hasattr(pp, "arrete")
        assert pp.arrete.modele == detr_arrete_modele
        assert hasattr(pp, "lettre")
        assert pp.lettre.modele == detr_lettre_modele

    key, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"  # ZIP (6 docs)
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        assert len(zf.namelist()) == 6


## Export-format coverage — end-to-end through the wizard


@freeze_time("2026-05-03")
def test_export_one_pdf_per_doc_single_returns_named_pdf(perimetre, detr_lettre_modele):
    """One projet × LETTRE → single PDF named after the document."""
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    pps = [
        ProgrammationProjetFactory(
            dotation_projet__projet__dossier_ds__perimetre=perimetre,
            dotation_projet__dotation=DOTATION_DETR,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            notified_at=None,
        )
    ]
    _drive_through_format_step(
        client,
        pps,
        modele_selection_fields={"modele_lettre_id": str(detr_lettre_modele.id)},
        export_format=EXPORT_FORMAT_ONE_PDF_PER_DOC,
    )
    response = _post_create_step(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    filename = os.path.basename(key)
    assert filename == pps[0].lettre.name
    assert body[:4] == b"%PDF"


@freeze_time("2026-05-03")
def test_export_one_pdf_per_doc_multi_returns_zip(
    client, programmation_projets, detr_lettre_modele
):
    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={"modele_lettre_id": str(detr_lettre_modele.id)},
        export_format=EXPORT_FORMAT_ONE_PDF_PER_DOC,
    )
    response = _post_create_step(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    assert os.path.basename(key) == "export turgot 03-05-2026.zip"
    assert body[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        assert len(zf.namelist()) == 3


@freeze_time("2026-05-03")
def test_export_one_pdf_all_merges_into_single_pdf(
    client, programmation_projets, detr_lettre_modele
):
    """One_PDF_ALL is only offered for a single document type (lettre xor arrêté)."""
    _drive_through_format_step(
        client,
        programmation_projets,
        modele_selection_fields={"modele_lettre_id": str(detr_lettre_modele.id)},
        export_format=EXPORT_FORMAT_ONE_PDF_ALL,
    )
    response = _post_create_step(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    assert os.path.basename(key) == "export lettre turgot 03-05-2026.pdf"
    assert body[:4] == b"%PDF"


@freeze_time("2026-05-03")
def test_export_one_pdf_per_project_single_returns_named_pdf(
    perimetre, detr_arrete_modele, detr_lettre_modele
):
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)
    pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    _drive_through_format_step(
        client,
        [pp],
        document_type=ARRETE_ET_LETTRE,
        modele_selection_fields={
            "modele_arrete_id": str(detr_arrete_modele.id),
            "modele_lettre_id": str(detr_lettre_modele.id),
        },
        export_format=EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    )
    response = _post_create_step(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    ds_number = pp.dossier.ds_number
    raison_sociale = slugify(pp.dossier.ds_demandeur.raison_sociale)
    expected = f"lettre et arrêté - {ds_number} - {raison_sociale} - 03-05-2026.pdf"
    assert os.path.basename(key) == expected
    assert body[:4] == b"%PDF"


@freeze_time("2026-05-03")
def test_export_one_pdf_per_project_multi_returns_zip(
    client, programmation_projets, detr_arrete_modele, detr_lettre_modele
):
    _drive_through_format_step(
        client,
        programmation_projets,
        document_type=ARRETE_ET_LETTRE,
        modele_selection_fields={
            "modele_arrete_id": str(detr_arrete_modele.id),
            "modele_lettre_id": str(detr_lettre_modele.id),
        },
        export_format=EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    )
    response = _post_create_step(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    assert os.path.basename(key) == "export turgot 03-05-2026.zip"
    assert body[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        # One merged PDF per project.
        assert len(zf.namelist()) == 3


@freeze_time("2026-05-03")
def test_export_one_pdf_all_grouped_merges_into_single_pdf(
    client, programmation_projets, detr_arrete_modele, detr_lettre_modele
):
    _drive_through_format_step(
        client,
        programmation_projets,
        document_type=ARRETE_ET_LETTRE,
        modele_selection_fields={
            "modele_arrete_id": str(detr_arrete_modele.id),
            "modele_lettre_id": str(detr_lettre_modele.id),
        },
        export_format=EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    )
    response = _post_create_step(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    assert os.path.basename(key) == "export turgot 03-05-2026.pdf"
    assert body[:4] == b"%PDF"

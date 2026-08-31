import io
import os
import zipfile
from html import unescape
from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings
from freezegun import freeze_time

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.forms import (
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_PER_DOC,
    GenerateDocumentsModeleSelectionForm,
)
from gsl_notification.models import ExportJob, LettreRefus
from gsl_notification.tests.factories import (
    LettreRefusFactory,
    ModeleLettreRefusFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, LETTRE_REFUS

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
        status=ProgrammationProjet.STATUS_REFUSED,
        montant=0,
        dotation_projet__projet__notified_at=None,
    )


@pytest.fixture
def detr_refus_modele(perimetre):
    return ModeleLettreRefusFactory(dotation=DOTATION_DETR, perimetre=perimetre)


@pytest.fixture
def client(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture(autouse=True)
def _mock_logo_base64():
    """Step_create renders every PDF synchronously, which fetches the modele
    logo via HTTP. Mock it so tests don't hit the network."""
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        yield


## Helpers


HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}

WIZARD_PREFIX_DETR = f"generate_lettre_refus_wizard_{DOTATION_DETR}"


def _wizard_url(dotation=DOTATION_DETR):
    from django.urls import reverse

    return reverse("gsl_notification:generate-refus-documents-modal", args=[dotation])


def _status_url(dotation, job_id):
    from django.urls import reverse

    return reverse(
        "gsl_notification:generate-refus-documents-status",
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
            "launch", fields, prefix=f"generate_lettre_refus_wizard_{dotation}"
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
    return {t.name for t in response.templates}


TEMPLATE_BASE = "gsl_notification/generated_document/multiple_wizard/"


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


def test_launch_with_valid_ids_renders_step_modele_dialog(
    client, programmation_projets
):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    response = _post_launch(client, ids=ids)
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_modele_selection.html"
    assert "HX-Location" not in response.headers


def test_launch_skips_type_selection_and_sets_document_type_lettre_refus(
    client, programmation_projets
):
    """GenerateLettreRefusWizard declares no type_selection step: the launch
    step jumps straight to modele_selection, with document_type already fixed
    to LETTRE_REFUS."""
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    response = _post_launch(client, ids=ids)
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_modele_selection.html"
    assert response.context["form"].document_type == LETTRE_REFUS


def test_launch_no_projects_renders_error_body(client):
    response = _post_launch(client, ids="")
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_launch.html"
    form = response.context["form"]
    assert "Aucun projet à notifier." in " ".join(form.errors.get("ids", []))


def test_launch_wrong_perimetre_renders_error_body(client):
    wrong_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_REFUSED,
        montant=0,
        dotation_projet__projet__notified_at=None,
    )
    response = _post_launch(client, ids=str(wrong_pp.id))
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_launch.html"
    form = response.context["form"]
    assert "choix valide" in " ".join(form.errors.get("ids", []))


def test_launch_ignores_ineligible_ids_silently(client, programmation_projets):
    """A selection mixing eligible (refused) and ineligible (accepted) rows
    must not fail validation: the ineligible one is silently dropped."""
    accepted_pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=programmation_projets[
            0
        ].dossier.perimetre,
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        dotation_projet__projet__notified_at=None,
    )
    ids = ",".join([str(pp.id) for pp in programmation_projets] + [str(accepted_pp.id)])
    response = _post_launch(client, ids=ids)
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_modele_selection.html"
    assert "form" not in response.context or not response.context["form"].errors


## Wizard step submissions


def _open_wizard_at_step_modele(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    _post_launch(client, ids=ids)
    return ids


def test_wizard_step_modele_missing_modele_re_renders_step(
    client, programmation_projets
):
    _open_wizard_at_step_modele(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data("modele_selection", {"modele_refus_id": ""}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_modele_selection.html"
    form = response.context["form"]
    assert form.errors["modele_refus_id"] == ["Veuillez sélectionner un modèle."]


def test_wizard_step_modele_to_step_format(
    client, programmation_projets, detr_refus_modele
):
    _open_wizard_at_step_modele(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection", {"modele_refus_id": str(detr_refus_modele.id)}
        ),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_form_step.html"


def test_wizard_step_format_invalid_export_format_re_renders_step(
    client, programmation_projets, detr_refus_modele
):
    _open_wizard_at_step_modele(client, programmation_projets)
    client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection", {"modele_refus_id": str(detr_refus_modele.id)}
        ),
        **HTMX_HEADERS,
    )
    response = client.post(
        _wizard_url(),
        _wizard_step_data("format", {"export_format": ""}),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_form_step.html"
    form = response.context["form"]
    assert "Veuillez sélectionner un format d'export." in " ".join(
        form["export_format"].errors
    )


## Step create — final wizard step (loading body + auto-submit → done)


def _drive_through_step_format(
    client,
    programmation_projets,
    *,
    modele_id,
    overwrite_strategy=None,
    export_format=EXPORT_FORMAT_ONE_PDF_PER_DOC,
    dotation=DOTATION_DETR,
):
    """Walk the wizard from launch through a step_format submit.

    Returns the response of the step_format POST (= initial step_create render).
    """
    _open_wizard_at_step_modele(client, programmation_projets)
    step_modele_fields = {"modele_refus_id": str(modele_id)}
    if overwrite_strategy:
        step_modele_fields["overwrite_strategy"] = overwrite_strategy
    client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "modele_selection",
            step_modele_fields,
            prefix=f"generate_lettre_refus_wizard_{dotation}",
        ),
        **HTMX_HEADERS,
    )
    return client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "format",
            {"export_format": export_format},
            prefix=f"generate_lettre_refus_wizard_{dotation}",
        ),
        **HTMX_HEADERS,
    )


def _post_step_create_raw(client, dotation=DOTATION_DETR):
    """POST step_create and return the intermediate polling response."""
    return client.post(
        _wizard_url(dotation),
        _wizard_step_data(
            "create", {}, prefix=f"generate_lettre_refus_wizard_{dotation}"
        ),
        **HTMX_HEADERS,
    )


def _post_step_create(client, dotation=DOTATION_DETR):
    """POST step_create then poll the status endpoint; returns the final success
    response."""
    polling_response = _post_step_create_raw(client, dotation)
    job_id = polling_response.context["job_id"]
    return client.get(_status_url(dotation, job_id), **HTMX_HEADERS)


def test_wizard_step_format_renders_loading_body(
    client, programmation_projets, detr_refus_modele
):
    response = _drive_through_step_format(
        client, programmation_projets, modele_id=detr_refus_modele.id
    )
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_loading.html"
    assert response.context["doc_count"] == 3
    assert b"generate_lettre_refus_wizard_DETR-current_step" in response.content
    assert b'value="create"' in response.content


def test_wizard_step_create_returns_polling_template(
    client, programmation_projets, detr_refus_modele
):
    _drive_through_step_format(
        client, programmation_projets, modele_id=detr_refus_modele.id
    )
    response = _post_step_create_raw(client)
    assert response.status_code == 200
    assert TEMPLATE_BASE + "modal_export_progress.html" in _template_names(response)
    assert "job_id" in response.context
    assert "job" in response.context


def test_wizard_step_create_creates_documents_and_returns_success(
    client, programmation_projets, detr_refus_modele
):
    _drive_through_step_format(
        client, programmation_projets, modele_id=detr_refus_modele.id
    )
    response = _post_step_create(client)
    assert response.status_code == 200
    assert TEMPLATE_BASE + "modal_success.html" in _template_names(response)
    assert response.context["doc_count"] == 3
    assert len(list(response.context["refreshed_programmation_projets"])) == 3
    for pp in programmation_projets:
        pp.refresh_from_db()
        assert hasattr(pp, "refus")
        assert pp.refus.modele == detr_refus_modele
        assert pp.refus.created_by == client.user

    _, body = _read_storage_body(response.context["download_url"])
    assert body[:2] == b"PK"  # ZIP (3 docs)


def test_wizard_step_create_replaces_existing_doc(
    client, programmation_projets, detr_refus_modele
):
    pp = programmation_projets[0]
    old_refus = LettreRefusFactory(programmation_projet=pp)

    _drive_through_step_format(
        client,
        programmation_projets,
        modele_id=detr_refus_modele.id,
        overwrite_strategy=GenerateDocumentsModeleSelectionForm.STRATEGY_REMPLACER,
    )
    _post_step_create(client)
    pp.refresh_from_db()
    assert pp.refus.id != old_refus.id


def test_wizard_step_modele_conserver_when_all_covered_advances_to_step_format(
    client, programmation_projets, detr_refus_modele
):
    for pp in programmation_projets:
        LettreRefusFactory(programmation_projet=pp)

    _open_wizard_at_step_modele(client, programmation_projets)
    response = client.post(
        _wizard_url(),
        _wizard_step_data(
            "modele_selection",
            {
                "modele_refus_id": str(detr_refus_modele.id),
                "overwrite_strategy": GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
            },
        ),
        **HTMX_HEADERS,
    )
    assert response.status_code == 200
    assert response.templates[0].name == TEMPLATE_BASE + "modal_form_step.html"
    form = response.context["form"]
    assert "overwrite_strategy" not in form.errors
    # No new lettre created yet: only the original 3 fixtures remain.
    assert LettreRefus.objects.count() == 3


def test_wizard_step_create_conserver_creates_only_missing_documents(
    client, programmation_projets, detr_refus_modele
):
    pp_with_existing, *pps_without = programmation_projets
    old_refus = LettreRefusFactory(programmation_projet=pp_with_existing)

    _drive_through_step_format(
        client,
        programmation_projets,
        modele_id=detr_refus_modele.id,
        overwrite_strategy=GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
    )
    response = _post_step_create(client)
    assert response.status_code == 200
    assert TEMPLATE_BASE + "modal_success.html" in _template_names(response)

    pp_with_existing.refresh_from_db()
    assert pp_with_existing.refus.id == old_refus.id
    for pp in pps_without:
        pp.refresh_from_db()
        assert hasattr(pp, "refus")
        assert pp.refus.modele == detr_refus_modele


def test_wizard_step_create_remplacer_when_all_covered_replaces_all(
    client, programmation_projets, detr_refus_modele
):
    old_ids = []
    for pp in programmation_projets:
        old_ids.append(LettreRefusFactory(programmation_projet=pp).id)

    _drive_through_step_format(
        client,
        programmation_projets,
        modele_id=detr_refus_modele.id,
        overwrite_strategy=GenerateDocumentsModeleSelectionForm.STRATEGY_REMPLACER,
    )
    response = _post_step_create(client)
    assert response.status_code == 200
    assert TEMPLATE_BASE + "modal_success.html" in _template_names(response)
    for pp, old_id in zip(programmation_projets, old_ids, strict=True):
        pp.refresh_from_db()
        assert pp.refus.id != old_id
        assert pp.refus.modele == detr_refus_modele


def test_export_job_attr_names_and_document_type(
    client, programmation_projets, detr_refus_modele
):
    _drive_through_step_format(
        client, programmation_projets, modele_id=detr_refus_modele.id
    )
    _post_step_create(client)
    job = ExportJob.objects.latest("created_at")
    assert job.attr_names == [LETTRE_REFUS]
    assert job.document_type == LETTRE_REFUS


## Export-format coverage


@freeze_time("2026-05-03")
def test_export_one_pdf_per_doc_multi_returns_zip(
    client, programmation_projets, detr_refus_modele
):
    _drive_through_step_format(
        client,
        programmation_projets,
        modele_id=detr_refus_modele.id,
        export_format=EXPORT_FORMAT_ONE_PDF_PER_DOC,
    )
    response = _post_step_create(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    assert os.path.basename(key) == "export turgot 03-05-2026.zip"
    assert body[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        assert len(zf.namelist()) == 3


@freeze_time("2026-05-03")
def test_export_one_pdf_all_merges_into_single_pdf(
    client, programmation_projets, detr_refus_modele
):
    _drive_through_step_format(
        client,
        programmation_projets,
        modele_id=detr_refus_modele.id,
        export_format=EXPORT_FORMAT_ONE_PDF_ALL,
    )
    response = _post_step_create(client)
    assert response.status_code == 200

    key, body = _read_storage_body(response.context["download_url"])
    assert os.path.basename(key) == "export lettre de refus turgot 03-05-2026.pdf"
    assert body[:4] == b"%PDF"

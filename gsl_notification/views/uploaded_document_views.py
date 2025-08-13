from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods

from gsl_notification.models import (
    Annexe,
    ArreteSigne,
)
from gsl_notification.utils import (
    get_s3_object,
    get_uploaded_document_class,
    get_uploaded_form_class,
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_notification.views.decorators import (
    arrete_signe_visible_by_user,
    document_visible_by_user,
    programmation_projet_visible_by_user,
)
from gsl_notification.views.views import (
    _enrich_context_for_create_or_get_arrete_view,
    _redirect_to_documents_view,
)
from gsl_programmation.models import ProgrammationProjet


@require_http_methods(["GET"])
@programmation_projet_visible_by_user
def choose_type_for_document_upload(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    context = {"programmation_projet": programmation_projet}
    return render(
        request,
        "gsl_notification/uploaded_document/choose_upload_document_type.html",
        context=context,
    )


# Upload document ------------------------------------------------------------------


@programmation_projet_visible_by_user
@require_http_methods(["GET", "POST"])
def create_uploaded_document_view(request, programmation_projet_id, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    uploaded_doc_class = get_uploaded_document_class(document_type)
    uploaded_doc_form = get_uploaded_form_class(document_type)

    if request.method == "POST":
        form = uploaded_doc_form(request.POST, request.FILES)
        if form.is_valid():
            update_file_name_to_put_it_in_a_programmation_projet_folder(
                form.instance.file,
                programmation_projet.id,
                is_annexe=uploaded_doc_class == Annexe,
            )
            form.save()

            return _redirect_to_documents_view(request, programmation_projet.id)
    else:
        form = uploaded_doc_form()

    context = {"form": form, "document_type": document_type}
    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )

    return render(
        request,
        "gsl_notification/uploaded_document/upload_document.html",
        context=context,
    )


# Suppression d'arrêté signé ----------------------------------------------------------


@document_visible_by_user
@require_http_methods(["POST"])
def delete_uploaded_document_view(request, document_type, document_id):
    doc_class = get_uploaded_document_class(document_type)
    doc = get_object_or_404(doc_class, id=document_id)
    programmation_projet_id = doc.programmation_projet.id

    doc.delete()

    return _redirect_to_documents_view(request, programmation_projet_id)


# TODO remove arrete_signe_visible_by_user
@arrete_signe_visible_by_user
@require_GET
def download_arrete_signe(request, arrete_signe_id, download=True):
    arrete = get_object_or_404(ArreteSigne, id=arrete_signe_id)
    s3_object = get_s3_object(arrete.file.name)

    response = StreamingHttpResponse(
        iter(s3_object["Body"].iter_chunks()),
        content_type=s3_object["ContentType"],
    )
    response["Content-Disposition"] = (
        f'{"attachment" if download else "inline"}; filename="{arrete.file.name.split("/")[-1]}"'
    )
    return response


@arrete_signe_visible_by_user
@require_GET
def view_arrete_signe(request, arrete_signe_id):
    return download_arrete_signe(request, arrete_signe_id, False)

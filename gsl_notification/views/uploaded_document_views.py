from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from django.views.generic import UpdateView

from gsl_core.exceptions import Http404
from gsl_notification.forms import ChooseDocumentTypeForUploadForm
from gsl_notification.models import (
    Annexe,
)
from gsl_notification.utils import (
    get_s3_object,
    get_uploaded_document_class,
    get_uploaded_form_class,
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_notification.views.views import (
    _enrich_context_for_create_or_get_arrete_view,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import PROJET_STATUS_ACCEPTED
from gsl_projet.models import Projet


class ChooseDocumentTypeForUploadView(LoginRequiredMixin, UpdateView):
    model = Projet
    template_name = (
        "gsl_notification/uploaded_document/choose_upload_document_type.html"
    )
    form_class = ChooseDocumentTypeForUploadForm
    pk_url_kwarg = "projet_id"

    def get_queryset(self):
        # Only projects visible to user with accepted dotations
        return (
            Projet.objects.for_user(self.request.user)
            .filter(dotationprojet__status=PROJET_STATUS_ACCEPTED)
            .distinct()
        )

    def form_valid(self, form):
        document = form.cleaned_data["document"]
        return redirect(
            "gsl_notification:upload-a-document",
            projet_id=self.object.pk,
            dotation=document["dotation"],
            document_type=document["type"],
        )


# Upload document ------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def create_uploaded_document_view(request, projet_id, dotation, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet.objects.visible_to_user(request.user),
        dotation_projet__projet_id=projet_id,
        enveloppe__dotation=dotation,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    try:
        uploaded_doc_class = get_uploaded_document_class(document_type)
    except ValueError:
        raise Http404(user_message="Le type de document sélectionné n'existe pas.")
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

            return redirect(
                reverse(
                    "gsl_notification:documents",
                    kwargs={"projet_id": projet_id},
                )
            )
    else:
        form = uploaded_doc_form()

    context = {
        "form": form,
        "document_type": document_type,
        "dotation": dotation,
    }
    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )

    return render(
        request,
        "gsl_notification/uploaded_document/upload_document.html",
        context=context,
    )


@require_GET
def download_uploaded_document(request, document_type, document_id, download=True):
    try:
        doc_class = get_uploaded_document_class(document_type)
    except ValueError:
        raise Http404(user_message="Le type de document sélectionné n'existe pas.")
    doc = get_object_or_404(
        doc_class.objects.filter(
            programmation_projet__dotation_projet__projet__in=Projet.objects.for_user(
                request.user
            )
        ),
        id=document_id,
    )

    if not settings.BYPASS_ANTIVIRUS:
        if doc.is_infected:
            raise Http404(
                user_message="Ce fichier ne peut pas être téléchargé car il a été identifié comme infecté."
            )
        if doc.last_scan is None:
            raise Http404(
                user_message="Ce fichier est en cours d'analyse antivirus. Veuillez réessayer dans quelques instants."
            )

    s3_object = get_s3_object(doc.file.name)

    response = StreamingHttpResponse(
        iter(s3_object["Body"].iter_chunks()),
        content_type=s3_object["ContentType"],
    )
    response["Content-Disposition"] = (
        f'{"attachment" if download else "inline"}; filename="{doc.file.name.split("/")[-1]}"'
    )
    return response


@require_GET
def view_uploaded_document(request, document_type, document_id):
    return download_uploaded_document(request, document_type, document_id, False)

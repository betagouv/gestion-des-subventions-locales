from django.conf import settings
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from gsl.projet.models import Projet
from gsl_core.exceptions import Http404
from gsl_notification.models import UPLOADED_DOCUMENTS
from gsl_notification.utils import get_s3_object


@require_GET
def download_uploaded_document(request, document_type, document_id, download=True):
    doc_class = UPLOADED_DOCUMENTS.get(document_type)
    if doc_class is None:
        raise Http404(user_message="Le type de document sélectionné n'existe pas.")
    doc = get_object_or_404(
        doc_class.objects.filter(
            programmation_projet__dotation_projet__projet__in=Projet.objects.active().for_user(
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

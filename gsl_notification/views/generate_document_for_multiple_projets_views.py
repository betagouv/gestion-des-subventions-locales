import io
import logging
import zipfile

from django.http import HttpResponse
from django.shortcuts import get_list_or_404, get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView
from django_htmx.http import trigger_client_event

from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404, PermissionDenied
from gsl_notification.utils import (
    generate_pdf_for_generated_document,
    get_generated_document_class,
    get_modele_class,
    get_modele_perimetres,
    get_programmation_projet_attribute,
    replace_mentions_in_html,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import (
    ARRETE,
    DOTATIONS,
    LETTRE,
)
from gsl_projet.models import Projet

logger = logging.getLogger(__name__)


DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR = "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."


@require_GET
def download_documents(request, dotation, document_type):
    if dotation not in DOTATIONS:
        raise Http404(user_message="Dotation inconnue")
    if document_type not in [ARRETE, LETTRE]:
        raise Http404(user_message="Type de document inconnu")

    pp_attr = get_programmation_projet_attribute(document_type)
    attr_select_related = [
        "dotation_projet",
        "dotation_projet__projet",
        "dotation_projet__projet__dossier_ds",
        pp_attr,
        f"{pp_attr}__modele",
    ]

    try:
        ids = _get_pp_ids(request)
        programmation_projets = get_list_or_404(
            ProgrammationProjet.objects.select_related(*attr_select_related),
            id__in=ids,
            dotation_projet__dotation=dotation,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            dotation_projet__projet__notified_at=None,
        )
        if len(programmation_projets) < len(ids):
            raise Http404(
                user_message=DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
            )

        _check_if_projets_are_accessible_for_user(request, programmation_projets)
    except ValueError:
        filterset = ProgrammationProjetFilters(
            data=request.GET,
            request=request,
        )
        programmation_projets = filterset.qs.to_notify().select_related(
            *attr_select_related
        )

    try:
        documents = set(getattr(pp, pp_attr) for pp in programmation_projets)
    except (
        ProgrammationProjet.lettre_notification.RelatedObjectDoesNotExist,
        ProgrammationProjet.arrete.RelatedObjectDoesNotExist,
    ):
        raise Http404(user_message="Un des projets n'a pas le document demandé.")

    if len(documents) == 1:
        document = next(iter(documents))
        pdf_content = generate_pdf_for_generated_document(document)
        logger.info(f"#1 {document} généré")
        response = HttpResponse(pdf_content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{document.name}"'
        return response

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            pdf_content = generate_pdf_for_generated_document(document)
            filename = f"{document.name}"
            zip_file.writestr(filename, pdf_content)
            logger.info(f"#{i} {document} généré")
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="documents.zip"'
    return response


# Utils


def _get_pp_ids(request):
    ids_str = request.GET.get("ids") or request.POST.get("ids")
    if not ids_str:
        raise ValueError("Aucun id de programmation projet")

    ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
    return ids


def _check_if_projets_are_accessible_for_user(request, programmation_projets):
    projet_ids = set(pp.projet.id for pp in programmation_projets)
    projet_ids_visible_by_user = Projet.objects.for_user(request.user).filter(
        id__in=projet_ids
    )

    if len(projet_ids) != len(projet_ids_visible_by_user):
        raise PermissionDenied(
            user_message="Un ou plusieurs projets sont hors de votre périmètre."
        )


# Modal HTMX views

GENERATE_DOCUMENTS_MODAL_ID = "generate-multiple-modal"
GENERATE_DOCUMENTS_MODAL_BUTTON_ID = "generate-multiple-modal-btn"


class GenerateDocumentsModalMixin:
    http_method_names = ["post"]
    modal_id = GENERATE_DOCUMENTS_MODAL_ID

    def dispatch(self, request, *args, **kwargs):
        if self.kwargs["dotation"] not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dotation"] = self.kwargs["dotation"]
        context["modal_id"] = self.modal_id
        return context

    def _get_modeles(self, document_type):
        dotation = self.kwargs["dotation"]
        perimetres = get_modele_perimetres(dotation, self.request.user.perimetre)
        return get_modele_class(document_type).objects.filter(
            dotation=dotation, perimetre__in=perimetres
        )

    @staticmethod
    def _get_document_type_label(document_type):
        return "arrêtés" if document_type == ARRETE else "lettres de notification"

    @staticmethod
    def _get_doc_name(document_type, count):
        if document_type == ARRETE:
            return "arrêté" if count == 1 else "arrêtés"
        return "lettre de notification" if count == 1 else "lettres de notification"


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalView(GenerateDocumentsModalMixin, TemplateView):
    template_name = "gsl_notification/generated_document/multiple/modal_step1.html"

    def post(self, request, *args, **kwargs):
        dotation = self.kwargs["dotation"]
        try:
            ids = _get_pp_ids(request)
            programmation_projets = get_list_or_404(
                ProgrammationProjet,
                id__in=ids,
                status=ProgrammationProjet.STATUS_ACCEPTED,
                dotation_projet__projet__notified_at=None,
                dotation_projet__dotation=dotation,
            )
            if len(programmation_projets) < len(ids):
                raise Http404(
                    user_message=DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
                )
            _check_if_projets_are_accessible_for_user(request, programmation_projets)
            ids = [pp.id for pp in programmation_projets]
        except ValueError:
            filterset = ProgrammationProjetFilters(data=request.GET, request=request)
            ids = [pp.id for pp in filterset.qs.to_notify()]

        if not ids:
            raise Http404(user_message="Aucun projet à notifier.")

        context = self.get_context_data(
            pp_count=len(ids),
            ids=",".join(str(i) for i in ids),
            modal_button_id=GENERATE_DOCUMENTS_MODAL_BUTTON_ID,
        )
        response = self.render_to_response(context)
        return trigger_client_event(
            response,
            "click",
            {"target": f"#{GENERATE_DOCUMENTS_MODAL_BUTTON_ID}"},
            after="settle",
        )


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalStep2View(GenerateDocumentsModalMixin, TemplateView):
    template_name = "gsl_notification/generated_document/multiple/modal_step2_body.html"

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get("document_type") not in [ARRETE, LETTRE]:
            raise Http404(user_message="Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        document_type = request.POST.get("document_type")
        context = self.get_context_data(
            document_type=document_type,
            document_type_label=self._get_document_type_label(document_type),
            modeles=self._get_modeles(document_type),
            ids=request.POST.get("ids", ""),
        )
        return self.render_to_response(context)


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalLoadingView(GenerateDocumentsModalMixin, TemplateView):
    template_name = (
        "gsl_notification/generated_document/multiple/modal_loading_body.html"
    )

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get("document_type") not in [ARRETE, LETTRE]:
            raise Http404(user_message="Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        document_type = request.POST.get("document_type")
        modele_id = request.POST.get("modele_id", "").strip()
        ids_str = request.POST.get("ids", "")

        if not modele_id:
            context = self.get_context_data(
                document_type=document_type,
                document_type_label=self._get_document_type_label(document_type),
                modeles=self._get_modeles(document_type),
                ids=ids_str,
                error="Veuillez sélectionner un modèle.",
            )
            return self.response_class(
                request=self.request,
                template=[
                    "gsl_notification/generated_document/multiple/modal_step2_body.html"
                ],
                context=context,
                using=self.template_engine,
            )

        ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
        context = self.get_context_data(
            document_type=document_type,
            modele_id=modele_id,
            ids=ids_str,
            pp_count=len(ids),
        )
        return self.render_to_response(context)


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalCreateView(GenerateDocumentsModalMixin, TemplateView):
    template_name = (
        "gsl_notification/generated_document/multiple/modal_success_body.html"
    )

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get("document_type") not in [ARRETE, LETTRE]:
            raise Http404(user_message="Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        dotation = self.kwargs["dotation"]
        document_type = request.POST.get("document_type")
        ids_str = request.POST.get("ids", "")
        modele_id = request.POST.get("modele_id", "").strip()

        ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
        if not ids:
            raise Http404(user_message="Aucun projet sélectionné.")

        programmation_projets = get_list_or_404(
            ProgrammationProjet,
            id__in=ids,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            dotation_projet__projet__notified_at=None,
            dotation_projet__dotation=dotation,
        )
        if len(programmation_projets) < len(ids):
            raise Http404(
                user_message=DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
            )
        _check_if_projets_are_accessible_for_user(request, programmation_projets)

        try:
            document_class = get_generated_document_class(document_type)
        except ValueError:
            raise Http404(user_message="Type de document inconnu")

        modele = get_object_or_404(
            get_modele_class(document_type),
            id=modele_id,
            dotation=dotation,
            perimetre__in=get_modele_perimetres(dotation, request.user.perimetre),
        )

        documents_list = self._create_documents(
            programmation_projets, document_class, modele
        )

        download_url = reverse(
            "gsl_notification:download-documents",
            kwargs={"dotation": dotation, "document_type": document_type},
            query={"ids": ids_str},
        )
        context = self.get_context_data(
            doc_count=len(documents_list),
            doc_name=self._get_doc_name(document_type, len(documents_list)),
            download_url=download_url,
        )
        return self.render_to_response(context)

    def _create_documents(self, programmation_projets, document_class, modele):
        documents_list = []
        for pp in programmation_projets:
            try:
                document_class.objects.get(programmation_projet_id=pp.id).delete()
            except document_class.DoesNotExist:
                pass
            document = document_class(
                programmation_projet=pp,
                modele=modele,
                created_by=self.request.user,
                content=replace_mentions_in_html(modele.content, pp),
            )
            document.save()
            documents_list.append(document)
        return documents_list

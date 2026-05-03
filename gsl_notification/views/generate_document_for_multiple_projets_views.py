import datetime
import io
import logging
import zipfile

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404 as DjangoHttp404
from django.http import HttpResponse
from django.shortcuts import get_list_or_404, get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView
from django_htmx.http import trigger_client_event
from pikepdf import Pdf

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

# Modal HTMX views

GENERATE_DOCUMENTS_MODAL_ID = "generate-multiple-modal"
GENERATE_DOCUMENTS_MODAL_BUTTON_ID = "generate-multiple-modal-btn"
ARRETE_ET_LETTRE = "arrete_et_lettre"
VALID_DOCUMENT_TYPES = [ARRETE, LETTRE, ARRETE_ET_LETTRE]

EXPORT_FORMAT_ONE_PDF_PER_DOC = "un_pdf_par_document"
EXPORT_FORMAT_ONE_PDF_ALL = "un_seul_pdf_ensemble"
EXPORT_FORMAT_ONE_PDF_PER_PROJECT = "un_pdf_par_projet"
EXPORT_FORMAT_ONE_PDF_ALL_GROUPED = "un_seul_pdf_groupe_par_projet"

VALID_EXPORT_FORMATS_SINGLE = [EXPORT_FORMAT_ONE_PDF_PER_DOC, EXPORT_FORMAT_ONE_PDF_ALL]
VALID_EXPORT_FORMATS_BOTH = [
    EXPORT_FORMAT_ONE_PDF_PER_DOC,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
]


@require_GET
def download_documents(request, dotation, document_type):
    if dotation not in DOTATIONS:
        raise Http404(user_message="Dotation inconnue")
    if document_type not in [ARRETE, LETTRE, ARRETE_ET_LETTRE]:
        raise Http404(user_message="Type de document inconnu")

    types = [LETTRE, ARRETE] if document_type == ARRETE_ET_LETTRE else [document_type]
    attrs = [get_programmation_projet_attribute(t) for t in types]
    attr_select_related = [
        "dotation_projet",
        "dotation_projet__projet",
        "dotation_projet__projet__dossier_ds",
        "dotation_projet__projet__dossier_ds__ds_demandeur",
        *attrs,
        *(f"{a}__modele" for a in attrs),
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
        filterset = ProgrammationProjetFilters(data=request.GET, request=request)
        programmation_projets = filterset.qs.can_generate_documents().select_related(
            *attr_select_related
        )

    export_format = request.GET.get("export_format", EXPORT_FORMAT_ONE_PDF_PER_DOC)

    if export_format == EXPORT_FORMAT_ONE_PDF_ALL:
        return _download_single_merged_pdf(
            programmation_projets, attrs, document_type, request.user
        )
    if export_format == EXPORT_FORMAT_ONE_PDF_PER_PROJECT:
        return _download_one_pdf_per_project(programmation_projets, attrs, request.user)
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED:
        return _download_grouped_merged_pdf(programmation_projets, attrs, request.user)

    return _download_one_pdf_per_doc(programmation_projets, attrs)


def _download_one_pdf_per_doc(programmation_projets, attrs):
    try:
        documents = [
            doc
            for attr in attrs
            for doc in (getattr(pp, attr) for pp in programmation_projets)
        ]
    except (
        ProgrammationProjet.lettre_notification.RelatedObjectDoesNotExist,
        ProgrammationProjet.arrete.RelatedObjectDoesNotExist,
    ):
        raise Http404(user_message="Un des projets n'a pas le document demandé.")

    if len(documents) == 1:
        document = documents[0]
        pdf_content = generate_pdf_for_generated_document(document)
        logger.info(f"#1 {document} généré")
        response = HttpResponse(pdf_content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{document.name}"'
        return response

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            pdf_content = generate_pdf_for_generated_document(document)
            zip_file.writestr(f"{document.name}", pdf_content)
            logger.info(f"#{i} {document} généré")
    zip_buffer.seek(0)
    date_str = datetime.date.today().strftime("%d-%m-%Y")
    zip_filename = f"export turgot {date_str}.zip"
    response = HttpResponse(zip_buffer, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


def _download_single_merged_pdf(programmation_projets, attrs, document_type, user):
    pdf_bytes_list = []
    for pp in programmation_projets:
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(getattr(pp, attr))
            )
    merged = _merge_pdfs_bytes(pdf_bytes_list)
    date_str = datetime.date.today().strftime("%d-%m-%Y")
    doc_type_fr = "arrêté" if document_type == ARRETE else "lettre"
    filename = f"export {doc_type_fr} turgot {date_str}.pdf"
    response = HttpResponse(merged, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _download_one_pdf_per_project(programmation_projets, attrs, user):
    date_str = datetime.date.today().strftime("%d-%m-%Y")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for pp in programmation_projets:
            project_pdfs = [
                generate_pdf_for_generated_document(getattr(pp, attr)) for attr in attrs
            ]
            merged = _merge_pdfs_bytes(project_pdfs)
            ds_number = pp.dossier.ds_number
            raison_sociale = pp.dossier.ds_demandeur.raison_sociale
            filename = f"lettre et arrêté - {ds_number} - {raison_sociale}.pdf"
            zip_file.writestr(filename, merged)
    zip_buffer.seek(0)
    zip_filename = f"export turgot {date_str}.zip"
    response = HttpResponse(zip_buffer, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


def _download_grouped_merged_pdf(programmation_projets, attrs, user):
    pdf_bytes_list = []
    for pp in programmation_projets:
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(getattr(pp, attr))
            )
    merged = _merge_pdfs_bytes(pdf_bytes_list)
    date_str = datetime.date.today().strftime("%d-%m-%Y")
    filename = f"export turgot {date_str}.pdf"
    response = HttpResponse(merged, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _merge_pdfs_bytes(pdf_bytes_list: list[bytes]) -> bytes:
    pdf = Pdf.new()
    for pdf_bytes in pdf_bytes_list:
        src = Pdf.open(io.BytesIO(pdf_bytes))
        pdf.pages.extend(src.pages)
    output = io.BytesIO()
    pdf.save(output)
    output.seek(0)
    return output.read()


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


class GenerateDocumentsModalMixin:
    http_method_names = ["post"]
    modal_id = GENERATE_DOCUMENTS_MODAL_ID
    error_template_name = (
        "gsl_notification/generated_document/multiple/modal_error_body.html"
    )

    def dispatch(self, request, *args, **kwargs):
        if self.kwargs["dotation"] not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dotation"] = self.kwargs["dotation"]
        context["modal_id"] = self.modal_id
        return context

    @staticmethod
    def _error_message(exc, default):
        return getattr(exc, "user_message", None) or default

    def _render_error(self, error_message):
        context = self.get_context_data(error=error_message)
        return self.response_class(
            request=self.request,
            template=[self.error_template_name],
            context=context,
            using=self.template_engine,
        )

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
                _check_if_projets_are_accessible_for_user(
                    request, programmation_projets
                )
                ids = [pp.id for pp in programmation_projets]
            except ValueError:
                filterset = ProgrammationProjetFilters(
                    data=request.GET, request=request
                )
                ids = [pp.id for pp in filterset.qs.can_generate_documents()]

            if not ids:
                raise Http404(user_message="Aucun projet à notifier.")

            context = self.get_context_data(
                pp_count=len(ids),
                ids=",".join(str(i) for i in ids),
                modal_button_id=GENERATE_DOCUMENTS_MODAL_BUTTON_ID,
            )
        except (DjangoHttp404, DjangoPermissionDenied) as e:
            context = self.get_context_data(
                modal_button_id=GENERATE_DOCUMENTS_MODAL_BUTTON_ID,
                error=self._error_message(e, "Une erreur est survenue."),
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
        if request.POST.get("document_type") not in VALID_DOCUMENT_TYPES:
            return self._render_error("Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        document_type = request.POST.get("document_type")
        ids_str = request.POST.get("ids", "")
        if document_type == ARRETE_ET_LETTRE:
            context = self.get_context_data(
                document_type=document_type,
                modeles_arrete=self._get_modeles(ARRETE),
                modeles_lettre=self._get_modeles(LETTRE),
                ids=ids_str,
            )
        else:
            context = self.get_context_data(
                document_type=document_type,
                document_type_label=self._get_document_type_label(document_type),
                modeles=self._get_modeles(document_type),
                ids=ids_str,
            )
        return self.render_to_response(context)


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalStep3View(GenerateDocumentsModalMixin, TemplateView):
    template_name = "gsl_notification/generated_document/multiple/modal_step3_body.html"

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get("document_type") not in VALID_DOCUMENT_TYPES:
            return self._render_error("Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        document_type = request.POST.get("document_type")
        ids_str = request.POST.get("ids", "")
        modele_id = request.POST.get("modele_id", "").strip()
        modele_arrete_id = request.POST.get("modele_arrete_id", "").strip()
        modele_lettre_id = request.POST.get("modele_lettre_id", "").strip()

        if document_type == ARRETE_ET_LETTRE:
            if not modele_arrete_id or not modele_lettre_id:
                context = self.get_context_data(
                    document_type=ARRETE_ET_LETTRE,
                    modeles_arrete=self._get_modeles(ARRETE),
                    modeles_lettre=self._get_modeles(LETTRE),
                    ids=ids_str,
                    error="Veuillez sélectionner un modèle pour chaque type de document.",
                )
                return self.response_class(
                    request=self.request,
                    template=[
                        "gsl_notification/generated_document/multiple/modal_step2_body.html"
                    ],
                    context=context,
                    using=self.template_engine,
                )
        else:
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

        context = self.get_context_data(
            document_type=document_type,
            ids=ids_str,
            modele_id=modele_id,
            modele_arrete_id=modele_arrete_id,
            modele_lettre_id=modele_lettre_id,
        )
        return self.render_to_response(context)


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalLoadingView(GenerateDocumentsModalMixin, TemplateView):
    template_name = (
        "gsl_notification/generated_document/multiple/modal_loading_body.html"
    )

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get("document_type") not in VALID_DOCUMENT_TYPES:
            return self._render_error("Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        document_type = request.POST.get("document_type")
        ids_str = request.POST.get("ids", "")
        export_format = request.POST.get("export_format", "").strip()

        valid_formats = (
            VALID_EXPORT_FORMATS_BOTH
            if document_type == ARRETE_ET_LETTRE
            else VALID_EXPORT_FORMATS_SINGLE
        )
        if export_format not in valid_formats:
            context = self.get_context_data(
                document_type=document_type,
                ids=ids_str,
                modele_id=request.POST.get("modele_id", ""),
                modele_arrete_id=request.POST.get("modele_arrete_id", ""),
                modele_lettre_id=request.POST.get("modele_lettre_id", ""),
                error="Veuillez sélectionner un format d'export.",
            )
            return self.response_class(
                request=self.request,
                template=[
                    "gsl_notification/generated_document/multiple/modal_step3_body.html"
                ],
                context=context,
                using=self.template_engine,
            )

        ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
        doc_count = len(ids) * (2 if document_type == ARRETE_ET_LETTRE else 1)
        context = self.get_context_data(
            document_type=document_type,
            ids=ids_str,
            doc_count=doc_count,
            export_format=export_format,
            modele_id=request.POST.get("modele_id", ""),
            modele_arrete_id=request.POST.get("modele_arrete_id", ""),
            modele_lettre_id=request.POST.get("modele_lettre_id", ""),
        )
        return self.render_to_response(context)


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsModalCreateView(GenerateDocumentsModalMixin, TemplateView):
    template_name = (
        "gsl_notification/generated_document/multiple/modal_success_body.html"
    )

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get("document_type") not in VALID_DOCUMENT_TYPES:
            return self._render_error("Type de document inconnu")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            return self._post(request, *args, **kwargs)
        except (DjangoHttp404, DjangoPermissionDenied) as e:
            return self._render_error(
                self._error_message(
                    e, "Une erreur est survenue lors de la génération des documents."
                )
            )

    def _post(self, request, *args, **kwargs):
        dotation = self.kwargs["dotation"]
        document_type = request.POST.get("document_type")
        ids_str = request.POST.get("ids", "")
        export_format = request.POST.get("export_format", EXPORT_FORMAT_ONE_PDF_PER_DOC)

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

        if document_type == ARRETE_ET_LETTRE:
            return self._post_both_create(
                dotation, ids_str, programmation_projets, export_format
            )

        try:
            document_class = get_generated_document_class(document_type)
        except ValueError:
            raise Http404(user_message="Type de document inconnu")

        modele_id = request.POST.get("modele_id", "").strip()
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
            query={"ids": ids_str, "export_format": export_format},
        )
        updated_pps = ProgrammationProjet.objects.select_related(
            "arrete", "lettre_notification"
        ).filter(id__in=ids)
        context = self.get_context_data(
            document_type=document_type,
            doc_count=len(documents_list),
            doc_name=self._get_doc_name(document_type, len(documents_list)),
            download_url=download_url,
            programmation_projets=updated_pps,
        )
        return self.render_to_response(context)

    def _post_both_create(
        self, dotation, ids_str, programmation_projets, export_format
    ):
        perimetres = get_modele_perimetres(dotation, self.request.user.perimetre)
        modele_arrete = get_object_or_404(
            get_modele_class(ARRETE),
            id=self.request.POST.get("modele_arrete_id", "").strip(),
            dotation=dotation,
            perimetre__in=perimetres,
        )
        modele_lettre = get_object_or_404(
            get_modele_class(LETTRE),
            id=self.request.POST.get("modele_lettre_id", "").strip(),
            dotation=dotation,
            perimetre__in=perimetres,
        )
        arretes = self._create_documents(
            programmation_projets, get_generated_document_class(ARRETE), modele_arrete
        )
        lettres = self._create_documents(
            programmation_projets, get_generated_document_class(LETTRE), modele_lettre
        )
        download_url = reverse(
            "gsl_notification:download-documents",
            kwargs={"dotation": dotation, "document_type": ARRETE_ET_LETTRE},
            query={"ids": ids_str, "export_format": export_format},
        )
        pp_ids = [pp.id for pp in programmation_projets]
        updated_pps = ProgrammationProjet.objects.select_related(
            "arrete", "lettre_notification"
        ).filter(id__in=pp_ids)
        context = self.get_context_data(
            document_type=ARRETE_ET_LETTRE,
            doc_count=len(arretes) + len(lettres),
            download_url=download_url,
            programmation_projets=updated_pps,
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

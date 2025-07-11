import os

import boto3
from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.core.files.storage import FileSystemStorage
from django.http import Http404, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods
from django_weasyprint.views import WeasyTemplateResponse
from formtools.wizard.views import SessionWizardView

from gsl import settings
from gsl_notification.forms import (
    ArreteForm,
    ArreteSigneForm,
    ModeleArreteStepOneForm,
    ModeleArreteStepThreeForm,
    ModeleArreteStepTwoForm,
)
from gsl_notification.models import Arrete, ArreteSigne, ModeleArrete
from gsl_notification.utils import (
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_notification.views.decorators import (
    arrete_signe_visible_by_user,
    arrete_visible_by_user,
    programmation_projet_visible_by_user,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import DOTATIONS

# Views for listing notification documents on a programmationProjet, -------------------
# in various contexts


def _generic_documents_view(
    request, programmation_projet_id, source_url, template, context
):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )

    documents = {}

    try:
        documents["arrete"] = programmation_projet.arrete
    except Arrete.DoesNotExist:
        pass

    try:
        documents["arrete_signe"] = programmation_projet.arrete_signe
    except ArreteSigne.DoesNotExist:
        pass

    context.update(
        {
            "documents": documents,
            "programmation_projet_id": programmation_projet.id,
            "source_url": source_url,
            "dossier": programmation_projet.projet.dossier_ds,
        }
    )

    return render(
        request,
        template,
        context=context,
    )


@programmation_projet_visible_by_user
@require_GET
def documents_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    projet = programmation_projet.projet
    title = projet.dossier_ds.projet_intitule
    context = {
        "programmation_projet": programmation_projet,
        "dotation_projet": programmation_projet.dotation_projet,
        "projet": projet,
        "dossier": projet.dossier_ds,
        "title": title,
        "breadcrumb_dict": {
            "links": [
                {
                    "url": reverse("gsl_programmation:programmation-projet-list"),
                    "title": "Programmation en cours",
                },
            ],
            "current": title,
        },
    }

    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return _generic_documents_view(
        request,
        programmation_projet_id,
        programmation_projet.get_absolute_url(),
        "gsl_notification/tab_simulation_projet/tab_notifications.html",
        context,
    )


# Creation view from a model -----------------------------------------------------------
# @require_http_methods(["GET", "POST"])
# @programmation_projet_visible_by_user
# def create_arrete_view(request, programmation_projet_id):
#     # GET: list available models
#     # POST: create arrete instance from model and redirect to edit form
#     pass


# Edition form for arrêté --------------------------------------------------------------
@csp_update({"style-src": [SELF, UNSAFE_INLINE]})
@require_http_methods(["GET", "POST"])
@programmation_projet_visible_by_user
def change_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )

    if hasattr(programmation_projet, "arrete"):
        arrete = programmation_projet.arrete
        title = "Modification de l'arrêté"
    else:
        arrete = Arrete()
        title = "Création de l'arrêté"

    if request.method == "POST":
        form = ArreteForm(request.POST, instance=arrete)
        if form.is_valid():
            form.save()

            return _redirect_to_documents_view(request, programmation_projet.id)
        else:
            arrete = form.instance
    else:
        form = ArreteForm(instance=arrete)

    context = {
        "arrete_form": form,
        "arrete_initial_content": mark_safe(arrete.content),
        "page_title": title,
    }
    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return render(request, "gsl_notification/change_arrete.html", context=context)


# Suppression d'arrêté -----------------------------------------------------------------


@arrete_visible_by_user
@require_http_methods(["POST"])
def delete_arrete_view(request, arrete_id):
    arrete = get_object_or_404(Arrete, id=arrete_id)
    programmation_projet_id = arrete.programmation_projet.id

    arrete.delete()

    return _redirect_to_documents_view(request, programmation_projet_id)


# Upload arrêté signé ------------------------------------------------------------------


@programmation_projet_visible_by_user
@require_http_methods(["GET", "POST"])
def create_arrete_signe_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )

    if request.method == "POST":
        form = ArreteSigneForm(request.POST, request.FILES)
        if form.is_valid():
            update_file_name_to_put_it_in_a_programmation_projet_folder(
                form.instance.file, programmation_projet.id
            )
            form.save()

            return _redirect_to_documents_view(request, programmation_projet.id)
    else:
        form = ArreteSigneForm()

    context = {
        "arrete_signe_form": form,
    }
    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )

    return render(request, "gsl_notification/upload_arrete_signe.html", context=context)


# Download views -----------------------------------------------------------------------


@arrete_visible_by_user
@require_GET
def download_arrete(request, arrete_id):
    arrete = get_object_or_404(Arrete, id=arrete_id)
    context = {"content": mark_safe(arrete.content)}
    if settings.DEBUG and request.GET.get("debug", False):
        return TemplateResponse(
            template="gsl_notification/pdf/arrete.html",
            context=context,
            request=request,
        )

    return WeasyTemplateResponse(
        template="gsl_notification/pdf/arrete.html",
        context=context,
        request=request,
        filename=f"arrete-{arrete.id}.pdf",
    )


@arrete_signe_visible_by_user
@require_GET
def download_arrete_signe(request, arrete_signe_id):
    arrete = get_object_or_404(ArreteSigne, id=arrete_signe_id)
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    key = arrete.file.name

    try:
        s3_response = s3.get_object(Bucket=bucket, Key=key)
        response = StreamingHttpResponse(
            iter(s3_response["Body"].iter_chunks()),
            content_type=s3_response["ContentType"],
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{arrete.file.name.split("/")[-1]}"'
        )
        return response
    except s3.exceptions.NoSuchKey:
        raise Http404("Fichier non trouvé")


# utils --------------------------------------------------------------------------------


def _redirect_to_documents_view(request, programmation_projet_id):
    return redirect(
        reverse(
            "gsl_notification:documents",
            kwargs={"programmation_projet_id": programmation_projet_id},
        )
    )


def _enrich_context_for_create_or_get_arrete_view(
    context, programmation_projet, request
):
    context.update(
        {
            "programmation_projet": programmation_projet,
            "projet": programmation_projet.projet,
            "dossier": programmation_projet.projet.dossier_ds,
            "current_tab": "notifications",
        }
    )


# Create new ModeleArrete --------------------------------------------------------------


class CreateModelArreteWizard(SessionWizardView):
    form_list = (
        ModeleArreteStepOneForm,
        ModeleArreteStepTwoForm,
        ModeleArreteStepThreeForm,
    )
    template_name = "gsl_notification/modele_arrete/model_form.html"
    # Temporary storage
    file_storage = FileSystemStorage(
        location=os.path.join(settings.MEDIA_ROOT, "logos_modeles_arretes")
    )

    def dispatch(self, request, dotation, *args, **kwargs):
        if dotation not in DOTATIONS:
            return Http404("Dotation inconnue")
        perimetre = self.get_modele_perimetre(dotation, request.user.perimetre)
        self.instance = ModeleArrete(
            dotation=dotation, perimetre=perimetre, created_by=request.user
        )
        self.dotation = dotation
        response = super().dispatch(request, *args, **kwargs)
        return response

    def get_modele_perimetre(self, dotation, user_perimetre):
        return user_perimetre  # todo

    def done(self, form_list, **kwargs):
        instance: ModeleArrete = self.instance

        for form in form_list:
            print(form.cleaned_data)
            for key, value in form.cleaned_data.items():
                instance.__setattr__(key, value)

        instance.save()

        return HttpResponseRedirect("/page-to-redirect-to-when-done/")

    def get_form_instance(self, step):
        return self.instance

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context.update(
            {
                "dotation": self.dotation,
                "current_tab": self.dotation,
            }
        )
        step_titles = {
            "0": "Titre du modèle",
            "1": "En-tête du modèle",
            "2": "Contenu de l’arrêté pour le publipostage",
        }
        context.update(
            {
                "step_title": step_titles.get(self.steps.current, ""),
                "next_step_title": step_titles.get(self.steps.next, ""),
            }
        )
        return context

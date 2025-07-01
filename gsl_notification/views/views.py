import boto3
from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST
from django_weasyprint.views import WeasyTemplateResponse

from gsl import settings
from gsl_notification.forms import ArreteForm, ArreteSigneForm
from gsl_notification.models import Arrete, ArreteSigne
from gsl_notification.utils import (
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_notification.views.decorators import (
    arrete_signe_visible_by_user,
    arrete_visible_by_user,
    programmation_projet_visible_by_user,
)
from gsl_programmation.models import ProgrammationProjet

### Arrete


@csp_update({"style-src": [SELF, UNSAFE_INLINE]})
@programmation_projet_visible_by_user
def create_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    source_simulation_projet_id = request.GET.get("source_simulation_projet_id")

    if hasattr(programmation_projet, "arrete") or hasattr(
        programmation_projet, "arrete_signe"
    ):
        return _redirect_to_get_arrete_view(
            request, programmation_projet.id, source_simulation_projet_id
        )

    if request.method == "POST":
        form = ArreteForm(request.POST)
        if form.is_valid():
            form.save()

            return _redirect_to_get_arrete_view(
                request, programmation_projet.id, source_simulation_projet_id
            )
    else:
        form = ArreteForm()

    context = {
        "arrete_form": form,
        "arrete_signe_form": ArreteSigneForm(),
    }
    context = _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return render(request, "gsl_notification/create_arrete.html", context=context)


@csp_update({"style-src": [SELF, UNSAFE_INLINE]})
@programmation_projet_visible_by_user
def change_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    source_simulation_projet_id = request.GET.get("source_simulation_projet_id")

    if hasattr(programmation_projet, "arrete_signe"):
        return _redirect_to_get_arrete_view(
            request, programmation_projet.id, source_simulation_projet_id
        )

    if not hasattr(programmation_projet, "arrete"):
        url = reverse(
            "gsl_notification:create-arrete",
            kwargs={"programmation_projet_id": programmation_projet_id},
            query={"source_simulation_projet_id": source_simulation_projet_id},
        )
        return redirect(url)

    if request.method == "POST":
        form = ArreteForm(request.POST)
        if form.is_valid():
            form.save()

            return _redirect_to_get_arrete_view(
                request, programmation_projet.id, source_simulation_projet_id
            )
    else:
        arrete = programmation_projet.arrete
        form = ArreteForm(instance=arrete)

    context = {
        "arrete_form": form,
        "arrete_signe_form": ArreteSigneForm(),
    }
    context = _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return render(request, "gsl_notification/change_arrete.html", context=context)


@programmation_projet_visible_by_user
@require_GET
def get_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    try:
        arrete = programmation_projet.arrete_signe
    except ArreteSigne.DoesNotExist:
        try:
            arrete = programmation_projet.arrete
        except Arrete.DoesNotExist:
            return redirect(
                "gsl_notification:create-arrete",
                programmation_projet_id=programmation_projet.id,
            )
    context = {
        "arrete": arrete,
        "disabled_create_arrete_buttons": True,
        "programmation_projet_id": programmation_projet.id,
    }
    context = _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return render(request, "gsl_notification/get_arrete.html", context=context)


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


### ArreteSigne


@programmation_projet_visible_by_user
@require_POST
def create_arrete_signe_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    source_simulation_projet_id = request.GET.get("source_simulation_projet_id")

    form = ArreteSigneForm(request.POST, request.FILES)
    if form.is_valid():
        update_file_name_to_put_it_in_a_programmation_projet_folder(
            form.instance.file, programmation_projet.id
        )
        form.save()

        return _redirect_to_get_arrete_view(
            request, programmation_projet.id, source_simulation_projet_id
        )

    context = {
        "arrete_signe_form": form,
    }
    context = _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return render(request, "gsl_notification/create_arrete.html", context=context)


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


def _redirect_to_get_arrete_view(
    request, programmation_projet_id, source_simulation_projet_id=None
):
    url = reverse(
        "gsl_notification:get-arrete",
        kwargs={"programmation_projet_id": programmation_projet_id},
        query={"source_simulation_projet_id": source_simulation_projet_id},
    )
    return redirect(url)


def _enrich_context_for_create_or_get_arrete_view(
    context, programmation_projet, request
):
    context["stepper_dict"] = {
        "current_step_id": 1,
        "current_step_title": "1 - Création de l’arrêté",
        "next_step_title": "Ajout de la lettre de notification",
        "total_steps": 5,
    }
    context["programmation_projet"] = programmation_projet
    context["projet"] = programmation_projet.projet
    context["source_simulation_projet_id"] = request.GET.get(
        "source_simulation_projet_id", None
    )
    return context

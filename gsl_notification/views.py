import boto3
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from gsl import settings
from gsl_notification.forms import ArreteSigneForm
from gsl_notification.models import ArreteSigne
from gsl_notification.utils import (
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_programmation.models import ProgrammationProjet


def create_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    if hasattr(programmation_projet, "arrete_signe"):
        source_simulation_projet_id = request.GET.get("source_simulation_projet_id")
        return _redirect_to_get_arrete_view(
            request, programmation_projet.id, source_simulation_projet_id
        )

    if request.method == "POST":
        form = ArreteSigneForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.programmation_projet = programmation_projet
            form.instance.created_by = request.user
            update_file_name_to_put_it_in_a_programmation_projet_folder(
                form.instance.file, programmation_projet.id
            )
            form.save()

            source_simulation_projet_id = request.POST.get(
                "source_simulation_projet_id"
            )
            return _redirect_to_get_arrete_view(
                request, programmation_projet.id, source_simulation_projet_id
            )
    else:
        form = ArreteSigneForm()

    context = {
        "programmation_projet": programmation_projet,
        "form": form,
        "projet": programmation_projet.projet,
        "source_simulation_projet_id": request.GET.get(
            "source_simulation_projet_id", None
        ),
        "stepper_dict": {
            "current_step_id": 1,
            "current_step_title": "1 - Création de l’arrêté",
            "next_step_title": "Ajout de la lettre de notification",
            "total_steps": 5,
        },
    }
    return render(request, "create_arrete.html", context=context)


def get_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
    )
    try:
        arrete_signe = programmation_projet.arrete_signe
    except ArreteSigne.DoesNotExist:
        return redirect(
            "gsl_notification:create-arrete",
            programmation_projet_id=programmation_projet.id,
        )
    context = {
        "programmation_projet": programmation_projet,
        "arrete_signe": arrete_signe,
        "projet": programmation_projet.projet,
        "source_simulation_projet_id": request.GET.get(
            "source_simulation_projet_id", None
        ),
        "stepper_dict": {
            "current_step_id": 1,
            "current_step_title": "1 - Création de l’arrêté",
            "next_step_title": "Ajout de la lettre de notification",
            "total_steps": 5,
        },
    }
    return render(request, "get_arrete.html", context=context)


# TODO add restrictions !
def download_arrete_signe(request, arrete_signe_id):
    from gsl_notification.models import ArreteSigne

    arrete = ArreteSigne.objects.get(id=arrete_signe_id)
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
    )
    if source_simulation_projet_id:
        url += f"?source_simulation_projet_id={source_simulation_projet_id}"
    return redirect(url)

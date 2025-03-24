# Create your views here.
from celery import states
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST
from django.views.generic.list import ListView
from django_celery_results.models import TaskResult

from .models import Demarche, Dossier, FieldMappingForComputer
from .tasks import task_save_demarche_dossiers_from_ds, task_save_demarche_from_ds


@staff_member_required
@require_GET
def get_ds_demarches_from_numbers(request):
    return render(request, "gsl_demarches_simplifiees/get_demarches_from_numbers.html")


@staff_member_required
@require_POST
def post_get_ds_demarches_from_numbers(request):
    numbers_raw = request.POST.get("ds_numbers")
    number_of_demarches_in_the_pipe = 0
    for number in numbers_raw.split():
        if not number.isdigit():
            messages.error(
                request,
                f"{number} ne ressemble pas à un numéro de Démarche valide. Il a été ignoré.",
            )
            continue
        task_save_demarche_from_ds.delay(int(number))
        number_of_demarches_in_the_pipe += 1

    if number_of_demarches_in_the_pipe > 0:
        message = ngettext(
            "%(count)d démarche va être récupérée depuis DS.",
            "%(count)d démarches vont être récupérées depuis DS.",
            number_of_demarches_in_the_pipe,
        ) % {"count": number_of_demarches_in_the_pipe}
        messages.success(request, message)
    return redirect("ds:add-demarches")


@staff_member_required
def get_celery_task_results(request):
    tasks = TaskResult.objects.filter(
        task_name__in=(
            "gsl_demarches_simplifiees.tasks.task_save_demarche_from_ds",
            "gsl_demarches_simplifiees.tasks.task_save_demarche_dossiers_from_ds",
        ),
        status__in=(states.FAILURE, states.PENDING),
    )
    return render(
        request, "gsl_demarches_simplifiees/get_ds_tasks_status.html", {"tasks": tasks}
    )


class DemarcheListView(ListView):
    model = Demarche
    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Liste des démarches"
        return context


@staff_member_required
def get_demarche_mapping(request, demarche_ds_number):
    demarche = get_object_or_404(Demarche, ds_number=demarche_ds_number)
    context = {
        "demarche": demarche,
        "django_fields": Dossier.MAPPED_FIELDS,
        "existing_mappings": FieldMappingForComputer.objects.filter(demarche=demarche),
    }
    return render(request, "gsl_demarches_simplifiees/demarche_mapping.html", context)


@staff_member_required
def view_demarche_json(request, demarche_ds_number):
    demarche = get_object_or_404(Demarche, ds_number=demarche_ds_number)
    return JsonResponse(demarche.raw_ds_data or {})


@staff_member_required
def view_dossier_json(request, dossier_ds_number):
    dossier = get_object_or_404(Dossier, ds_number=dossier_ds_number)
    return JsonResponse(dossier.raw_ds_data or {})


@staff_member_required
@require_POST
def fetch_demarche_dossiers(request):
    demarche_ds_number = int(request.POST.get("demarche_ds_number"))
    task_save_demarche_dossiers_from_ds.delay(demarche_ds_number)
    return redirect("ds:liste-demarches")

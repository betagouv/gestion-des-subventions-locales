# Create your views here.
from celery import states
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST
from django.views.generic.list import ListView
from django_celery_results.models import TaskResult

from .models import Demarche
from .tasks import task_save_demarche_from_ds


@staff_member_required
@require_GET
def get_ds_demarches_from_numbers(request):
    return render(request, "gsl_ds/get_demarches_from_numbers.html")


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
        task_name="gsl_demarches_simplifiees.tasks.task_save_demarche_from_ds",
        status__in=(states.FAILURE, states.PENDING),
    )
    return render(request, "gsl_ds/get_ds_tasks_status.html", {"tasks": tasks})


class DemarcheListView(ListView):
    model = Demarche
    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Liste des démarches"
        return context

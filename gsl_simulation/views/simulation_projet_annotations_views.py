from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.generic.edit import UpdateView

from gsl_projet.forms import ProjetNoteForm
from gsl_projet.models import ProjetNote
from gsl_simulation.models import SimulationProjet
from gsl_simulation.views.decorators import exception_handler_decorator
from gsl_simulation.views.simulation_projet_views import (
    SimulationProjetDetailView,
    redirect_to_same_page_or_to_simulation_detail_by_default,
)


class SimulationProjetAnnotationsView(SimulationProjetDetailView):
    template_name = "gsl_simulation/tab_simulation_projet/tab_annotations.html"
    model = SimulationProjet

    def get_template_names(self):
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(
            with_specific_info_for_main_tab=False, **kwargs
        )
        context["projet_note_form"] = ProjetNoteForm()
        context["projet_notes"] = (
            self.object.projet.notes.select_related("created_by")
            .order_by("created_at")
            .all()
        )
        return context

    def post(self, request, *args, **kwargs):
        simulation_projet = get_object_or_404(
            SimulationProjet, id=self.kwargs.get("pk")
        )
        if request.POST.get("action") == "delete_note":
            return self.delete(request, *args, **kwargs)

        form = ProjetNoteForm(request.POST)

        if form.is_valid():
            projet_note = form.save(commit=False)
            projet_note.projet = simulation_projet.projet
            projet_note.created_by = request.user
            projet_note.save()
            messages.success(
                request,
                "La note a été ajoutée avec succès.",
                extra_tags="info",
            )
            return redirect_to_same_page_or_to_simulation_detail_by_default(
                request, simulation_projet
            )
        else:
            messages.error(
                request,
                "Une erreur s'est produite lors de la soumission du formulaire.",
                extra_tags="alert",
            )
            self.object = simulation_projet
            context = self.get_context_data(**kwargs)
            context["projet_note_form"] = form
            return render(request, self.template_name, context)

    def delete(self, request, *args, **kwargs):
        simulation_projet = get_object_or_404(
            SimulationProjet, id=self.kwargs.get("pk")
        )
        note_id = request.POST.get("note_id")
        if note_id:
            note = get_object_or_404(
                ProjetNote,
                pk=note_id,
                created_by=request.user,
                projet_id=simulation_projet.projet.id,
            )
            title = note.title
            note.delete()
            messages.success(
                request,
                f'La note "{title}" a bien été supprimée.',
                extra_tags="projet_note_deletion",
            )
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            request, simulation_projet
        )


class ProjetNoteEditView(UpdateView):
    model = ProjetNote
    form_class = ProjetNoteForm
    template_name = "htmx/projet_note_update_form.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request") != "true":
            return HttpResponseForbidden("Cette action n'est pas autorisée.")
        return [self.template_name]

    def dispatch(self, request, *args, **kwargs):
        self.simulation_projet_id = request.GET.get(
            "simulation_projet_id"
        ) or request.POST.get("simulation_projet_id")
        self.simulation_projet = get_object_or_404(
            SimulationProjet, id=self.simulation_projet_id
        )
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        self.obj = super().get_object(queryset)
        if self.obj.created_by != self.request.user:
            raise HttpResponseForbidden(
                "Vous n'avez pas la permission de modifier cette note."
            )
        return self.obj

    def get_success_url(self):
        messages.success(
            self.request,
            "La note a été mise à jour avec succès.",
            extra_tags="info",
        )
        return reverse(
            "gsl_simulation:simulation-projet-annotations",
            kwargs={"pk": self.simulation_projet_id},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["simulation_projet_id"] = self.simulation_projet_id
        return context


# TODO projet must be in user perimeter
@exception_handler_decorator
@require_GET
def get_note_card(request, pk: int, note_id: int):
    if request.headers.get("HX-Request") != "true":
        return HttpResponseForbidden("Cette action n'est pas autorisée.")
    return render(
        request,
        "includes/_note_card.html",
        {
            "note": get_object_or_404(ProjetNote, id=note_id),
            "simu": get_object_or_404(SimulationProjet, id=pk),
        },
    )

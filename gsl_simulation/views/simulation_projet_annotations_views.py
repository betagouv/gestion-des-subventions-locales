from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from gsl_projet.forms import ProjetNoteForm
from gsl_projet.models import ProjetNote
from gsl_simulation.models import SimulationProjet
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
        context["projet_notes"] = self.object.projet.notes.select_related(
            "created_by"
        ).all()
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
            note = ProjetNote.objects.get(pk=note_id)
            if note:
                if note.created_by != request.user:
                    return HttpResponseForbidden(
                        "Vous n'avez pas la permission de supprimer cette note."
                    )

                title = note.title
                note.delete()
                messages.success(
                    request,
                    f'La note "{title}" a bien été supprimée.',
                    extra_tags="projet_note_deletion",
                )
            else:
                messages.error(
                    request,
                    "La note n'a pas pu être trouvée.",
                    extra_tags="alert",
                )
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            request, simulation_projet
        )

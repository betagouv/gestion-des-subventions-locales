import os

from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db.models import ProtectedError
from django.db.models.fields import files
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView
from formtools.wizard.views import SessionWizardView

from gsl import settings
from gsl_core.models import Perimetre
from gsl_notification.forms import (
    ModeleArreteStepOneForm,
    ModeleArreteStepThreeForm,
    ModeleArreteStepTwoForm,
)
from gsl_notification.models import ModeleArrete
from gsl_notification.utils import (
    MENTION_TO_ATTRIBUTES,
    duplicate_field_file,
    get_modele_perimetres,
)
from gsl_notification.views.decorators import (
    modele_arrete_visible_by_user,
)
from gsl_projet.constants import DOTATIONS


class ModeleArreteListView(ListView):
    template_name = "gsl_notification/modele_arrete/list.html"

    def get_queryset(self):
        return ModeleArrete.objects.filter(
            dotation=self.dotation, perimetre__in=self.perimetres
        )

    def dispatch(self, request, dotation, *args, **kwargs):
        if dotation not in DOTATIONS:
            raise Http404("Dotation inconnue")
        self.perimetres = self.get_modele_perimetres(dotation, request.user.perimetre)
        self.dotation = dotation
        response = super().dispatch(request, *args, **kwargs)
        return response

    def get_modele_perimetres(self, dotation, user_perimetre) -> list[Perimetre]:
        return get_modele_perimetres(dotation, user_perimetre)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context.update(
            {
                "dotation": self.dotation,
                "current_tab": self.dotation,
                "modeles_list": [
                    {
                        "id": obj.id,
                        "name": obj.name,
                        "description": obj.description,
                        "actions": [
                            {
                                "label": "Modifier le modèle",
                                "href": reverse(
                                    "gsl_notification:modele-arrete-modifier",
                                    kwargs={"modele_arrete_id": obj.id},
                                ),
                            },
                            {
                                "label": "Dupliquer le modèle",
                                "href": reverse(
                                    "gsl_notification:modele-arrete-dupliquer",
                                    kwargs={"modele_arrete_id": obj.id},
                                ),
                                "class": "fr-btn--secondary",
                            },
                            {
                                "label": "Supprimer",
                                "class": "fr-btn--tertiary",
                                "aria_controls": "delete-modele-arrete",
                            },
                        ],
                    }
                    for obj in self.object_list
                ],
            }
        )
        return context


class CreateModelArreteWizard(SessionWizardView):
    form_list = (
        ModeleArreteStepOneForm,
        ModeleArreteStepTwoForm,
        ModeleArreteStepThreeForm,
    )
    # Temporary storage
    file_storage = FileSystemStorage(
        location=os.path.join(settings.MEDIA_ROOT, "logos_modeles_arretes")
    )

    @method_decorator(csp_update({"style-src": [SELF, UNSAFE_INLINE]}))
    def dispatch(
        self, request, dotation: str, instanciate_new_modele=True, *args, **kwargs
    ):
        if dotation not in DOTATIONS:
            raise Http404("Dotation inconnue")
        perimetre = request.user.perimetre
        if instanciate_new_modele:
            self.instance = ModeleArrete(
                dotation=dotation, perimetre=perimetre, created_by=request.user
            )
        self.dotation = dotation
        response = super().dispatch(request, *args, **kwargs)
        return response

    def done(self, form_list, **kwargs):
        instance: ModeleArrete = self.instance

        for form in form_list:
            for key, value in form.cleaned_data.items():
                instance.__setattr__(key, value)
                if key == "logo":
                    self._handle_logo(instance, value)

        instance.save()

        self._set_success_message(instance)

        return HttpResponseRedirect(
            reverse(
                "gsl_notification:modele-arrete-liste",
                kwargs={"dotation": self.dotation},
            )
        )

    def _handle_logo(self, instance, logo):
        pass

    def _set_success_message(self, instance):
        messages.success(
            self.request,
            f"Le modèle d’arrêté “{instance.name}” a bien été créé.",
        )

    def get_form_instance(self, step):
        return self.instance

    def get_form_initial(
        self,
        step,
    ):
        if not hasattr(self, "initial_instance"):
            if step == "2":
                return self.initial_dict.get(
                    step,
                    {
                        "content": mark_safe(
                            "<p>Écrivez ici le contenu de votre arrêté</p>"
                        )
                    },
                )
            return

        # if there is an initial_instance
        if step == "0":
            return self.initial_dict.get(
                step,
                {
                    "name": self.initial_instance.name,
                    "description": self.initial_instance.description,
                },
            )
        if step == "1":
            return self.initial_dict.get(
                step,
                {
                    "logo": self.initial_instance.logo,
                    "logo_alt_text": self.initial_instance.logo_alt_text,
                    "top_right_text": self.initial_instance.top_right_text,
                },
            )
        if step == "2":
            return self.initial_dict.get(
                step,
                {
                    "content": self.initial_instance.content,
                },
            )

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
                "mention_items": [
                    {"id": id, "label": MENTION_TO_ATTRIBUTES[id]["label"]}
                    for id in MENTION_TO_ATTRIBUTES.keys()
                ],
            }
        )
        return context

    def get_template_names(self):
        return f"gsl_notification/modele_arrete/modelearrete_form_step_{self.steps.current}.html"


class UpdateModeleArrete(CreateModelArreteWizard):
    @method_decorator(csp_update({"style-src": [SELF, UNSAFE_INLINE]}))
    def dispatch(
        self, request, modele_arrete_id, instanciate_new_modele=False, *args, **kwargs
    ):
        self.instance = get_object_or_404(
            ModeleArrete,
            id=modele_arrete_id,
        )
        dotation = self.instance.dotation
        self.possible_modele_perimetres = get_modele_perimetres(
            dotation, request.user.perimetre
        )
        if self.instance.perimetre not in self.possible_modele_perimetres:
            raise Http404("Modèle non existant")

        self.initial_instance = self.instance
        response = super().dispatch(
            request,
            dotation=dotation,
            instanciate_new_modele=instanciate_new_modele,
            *args,
            **kwargs,
        )
        return response

    def _handle_logo(self, instance, logo):
        if not isinstance(logo, files.FieldFile):
            old_instance = ModeleArrete.objects.get(pk=instance.pk)
            old_file = old_instance.logo
            old_file.delete(save=False)

    def _set_success_message(self, instance):
        messages.success(
            self.request,
            f"Le modèle d’arrêté “{instance.name}” a bien été modifié.",
        )


class DuplicateModeleArrete(UpdateModeleArrete):
    @method_decorator(csp_update({"style-src": [SELF, UNSAFE_INLINE]}))
    def dispatch(self, request, modele_arrete_id, *args, **kwargs):
        response = super().dispatch(
            request, modele_arrete_id, instanciate_new_modele=True, *args, **kwargs
        )
        return response

    def _handle_logo(self, instance, logo):
        if isinstance(logo, files.FieldFile):
            new_name, file_obj = duplicate_field_file(logo)
            if file_obj:
                instance.logo.save(new_name, file_obj, save=False)


@modele_arrete_visible_by_user
@require_http_methods(["POST"])
def delete_modele_arrete_view(request, modele_arrete_id):
    modele_arrete = get_object_or_404(ModeleArrete, id=modele_arrete_id)
    dotation = modele_arrete.dotation
    name = modele_arrete.name

    try:
        modele_arrete.delete()
        messages.info(
            request,
            f"Le modèle d’arrêté “{name}” a été supprimé.",
            extra_tags="delete-modele-arrete",
        )

    except ProtectedError:
        messages.error(
            request,
            f"Le modèle n'a pas été supprimé car il est utilisé par {modele_arrete.arrete_set.count()} arrêté(s).",
            extra_tags="alert",
        )

    return redirect(
        reverse("gsl_notification:modele-arrete-liste", kwargs={"dotation": dotation})
    )

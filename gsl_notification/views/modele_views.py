import os

from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db.models import ProtectedError
from django.db.models.fields import files
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods
from django.views.generic import FormView, ListView
from formtools.wizard.views import SessionWizardView

from gsl import settings
from gsl_core.models import Perimetre
from gsl_notification.forms import (
    ModeleDocumentStepOneForm,
    ModeleDocumentStepThreeForm,
    ModeleDocumentStepTwoForm,
    ModeleDocumentStepZeroForm,
)
from gsl_notification.models import (
    ModeleArrete,
    ModeleDocument,
    ModeleLettreNotification,
)
from gsl_notification.utils import (
    MENTION_TO_ATTRIBUTES,
    duplicate_field_file,
    get_modele_class,
    get_modele_perimetres,
)
from gsl_notification.views.decorators import modele_visible_by_user
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, DOTATIONS

TAG_LABEL_MAPPING = {
    ModeleDocument.TYPE_ARRETE: "Arrêté",
    ModeleDocument.TYPE_LETTRE: "Lettre de notification",
}


class ModeleListView(ListView):
    template_name = "gsl_notification/modele/list.html"

    def get_queryset(self):
        return sorted(
            list(
                ModeleArrete.objects.filter(
                    dotation=self.dotation, perimetre__in=self.perimetres
                )
            )
            + list(
                ModeleLettreNotification.objects.filter(
                    dotation=self.dotation, perimetre__in=self.perimetres
                )
            ),
            key=lambda modele: modele.created_at,
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
                        "type_label": TAG_LABEL_MAPPING[obj.type],
                        "type": obj.type,
                        "actions": [
                            {
                                "label": "Modifier le modèle",
                                "href": reverse(
                                    "gsl_notification:modele-modifier",
                                    kwargs={
                                        "modele_type": obj.type,
                                        "modele_id": obj.id,
                                    },
                                ),
                            },
                            {
                                "label": "Dupliquer le modèle",
                                "href": reverse(
                                    "gsl_notification:modele-dupliquer",
                                    kwargs={
                                        "modele_type": obj.type,
                                        "modele_id": obj.id,
                                    },
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


class ChooseModeleDocumentType(FormView):
    template_name = "gsl_notification/modele/choose_type.html"
    form_class = ModeleDocumentStepZeroForm

    def dispatch(self, request, dotation, *args, **kwargs):
        if dotation not in DOTATIONS:
            raise Http404("Dotation inconnue")
        self.dotation = dotation
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        modele_type = form.cleaned_data["type"]
        return redirect(
            reverse(
                "gsl_notification:modele-creer",
                kwargs={"modele_type": modele_type, "dotation": self.dotation},
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "dotation": self.dotation,
                "current_tab": self.dotation,
            }
        )
        return context


TEMPLATES = {
    "step_zero": "gsl_notification/modele/modele_form_step_1.html",
    "step_one": "gsl_notification/modele/modele_form_step_2.html",
    "step_two": "gsl_notification/modele/modele_form_step_3.html",
}


class CreateModelDocumentWizard(SessionWizardView):
    form_list = (
        ModeleDocumentStepOneForm,
        ModeleDocumentStepTwoForm,
        ModeleDocumentStepThreeForm,
    )

    # Temporary storage
    file_storage = FileSystemStorage(
        location=os.path.join(settings.MEDIA_ROOT, "logos_modeles_arretes")
    )

    @method_decorator(csp_update({"style-src": [SELF, UNSAFE_INLINE]}))
    def dispatch(
        self,
        request,
        modele_type: str,
        dotation: str,
        instanciate_new_modele=True,
        *args,
        **kwargs,
    ):
        if dotation not in DOTATIONS:
            raise Http404("Dotation inconnue")
        self.dotation = dotation
        self.modele_type = modele_type
        self._class = get_modele_class(modele_type)

        perimetre = request.user.perimetre
        if instanciate_new_modele:
            self.instance = self._class(
                dotation=dotation, perimetre=perimetre, created_by=request.user
            )
        response = super().dispatch(request, *args, **kwargs)
        return response

    def done(self, form_list, **kwargs):
        instance: ModeleLettreNotification | ModeleArrete = self.instance

        for form in form_list:
            for key, value in form.cleaned_data.items():
                instance.__setattr__(key, value)
                if key == "logo":
                    self._handle_logo(instance, value)

        instance.save()

        self._set_success_message(instance)

        return HttpResponseRedirect(
            reverse(
                "gsl_notification:modele-liste",
                kwargs={"dotation": self.dotation},
            )
        )

    def _handle_logo(self, instance, logo):
        pass

    def _set_success_message(self, instance, verbe="créé"):
        type_and_article = (
            "d’arrêté"
            if self.modele_type == ModeleDocument.TYPE_ARRETE
            else "de lettre de notification"
        )
        messages.success(
            self.request,
            f"Le modèle {type_and_article} “{instance.name}” a bien été {verbe}.",
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
                            "<p>Écrivez ici le contenu de votre modèle</p>"
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
                "type": self.modele_type,
                "dotation": self.dotation,
                "current_tab": self.dotation,
                "title": self._get_form_title(),
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
        return f"gsl_notification/modele/modele_form_step_{self.steps.current}.html"

    def _get_form_title(self):
        if self.modele_type == ModeleDocument.TYPE_ARRETE:
            return f"Création d’un nouveau modèle d'arrêté {self.dotation}"
        return f"Création d’un nouveau modèle de lettre de notification {self.dotation}"


class UpdateModele(CreateModelDocumentWizard):
    @method_decorator(csp_update({"style-src": [SELF, UNSAFE_INLINE]}))
    def dispatch(
        self,
        request,
        modele_type,
        modele_id,
        instanciate_new_modele=False,
        *args,
        **kwargs,
    ):
        self._class = get_modele_class(modele_type)
        self.instance = get_object_or_404(
            self._class,
            id=modele_id,
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
            modele_type=self.instance.type,
            instanciate_new_modele=instanciate_new_modele,
            *args,
            **kwargs,
        )
        return response

    def _handle_logo(self, instance, logo):
        if not isinstance(logo, files.FieldFile):
            old_instance = self._class.objects.get(pk=instance.pk)
            old_file = old_instance.logo
            old_file.delete(save=False)

    def _set_success_message(self, instance, verbe="modifié"):
        super()._set_success_message(instance, verbe)


class DuplicateModele(UpdateModele):
    @method_decorator(csp_update({"style-src": [SELF, UNSAFE_INLINE]}))
    def dispatch(self, request, modele_type, modele_id, *args, **kwargs):
        response = super().dispatch(
            request,
            modele_type,
            modele_id,
            instanciate_new_modele=True,
            *args,
            **kwargs,
        )
        return response

    def _handle_logo(self, instance, logo):
        if isinstance(logo, files.FieldFile):
            new_name, file_obj = duplicate_field_file(logo)
            if file_obj:
                instance.logo.save(new_name, file_obj, save=False)

    def _set_success_message(self, instance):
        super()._set_success_message(instance, verbe="créé")


@modele_visible_by_user
@require_http_methods(["POST"])
def delete_modele_view(request, modele_type, modele_id):
    _class = get_modele_class(modele_type)
    modele = get_object_or_404(_class, id=modele_id)
    dotation = modele.dotation
    name = modele.name

    try:
        modele.delete()
        type_and_article = (
            "d’arrêté"
            if modele_type == ModeleDocument.TYPE_ARRETE
            else "de lettre de notification"
        )

        messages.info(
            request,
            f"Le modèle {type_and_article} “{name}” a été supprimé.",
            extra_tags="delete-modele-arrete",
        )

    except ProtectedError:
        messages.error(
            request,
            # f"Le modèle n'a pas été supprimé car il est utilisé par {modele.arrete_set.count()} arrêté(s).", TODO => adapt to the model
            "Le modèle n'a pas été supprimé car il est utilisé par X arrêté(s).",
            extra_tags="alert",
        )

    return redirect(
        reverse("gsl_notification:modele-liste", kwargs={"dotation": dotation})
    )


@require_GET
def get_generic_modele(request, dotation):
    if dotation == DOTATION_DETR:
        return render(request, "gsl_notification/modele/generique/detr_modele.html")
    elif dotation == DOTATION_DSIL:
        return render(request, "gsl_notification/modele/generique/dsil_modele.html")
    raise Http404("Dotation inconnue")

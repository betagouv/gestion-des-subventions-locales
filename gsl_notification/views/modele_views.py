import os

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db.models import ProtectedError, Q
from django.db.models.fields import files
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.csp import CSP
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET
from django.views.generic import FormView, ListView
from django.views.generic.edit import DeleteView
from formtools.wizard.views import SessionWizardView

from gsl.utils.csp import csp_update
from gsl_core.exceptions import Http404
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_CREATION_MODELE,
    MATOMO_CATEGORY_MODELE,
)
from gsl_core.models import Perimetre
from gsl_notification.forms import (
    ModeleDocumentStepOneForm,
    ModeleDocumentStepThreeForm,
    ModeleDocumentStepTwoForm,
    ModeleDocumentStepZeroForm,
)
from gsl_notification.models import MODELES, ModeleDocument
from gsl_notification.utils import (
    MENTIONS,
    duplicate_field_file,
    get_modele_perimetres,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
)


class ModeleListView(ListView):
    template_name = "gsl_notification/modele/list.html"

    def get_queryset(self):
        return sorted(
            (
                modele
                for klass in MODELES.values()
                for modele in klass.objects.filter(
                    dotation=self.dotation, perimetre__in=self.perimetres
                ).defer("content", "top_right_text")
            ),
            key=lambda modele: modele.created_at,
        )

    def dispatch(self, request, dotation, *args, **kwargs):
        if dotation not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
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
                        "type_label": obj.type_label,
                        "type": obj.type,
                        "delete_title": obj.delete_title,
                        "delete_question": obj.delete_question,
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
            raise Http404(user_message="Dotation inconnue")
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

    @method_decorator(csp_update({"style-src": [CSP.SELF, CSP.UNSAFE_INLINE]}))
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
            raise Http404(user_message="Dotation inconnue")
        self.dotation = dotation
        self.modele_type = modele_type
        self._class = MODELES[self.modele_type]

        perimetre = request.user.perimetre
        if instanciate_new_modele:
            self.instance = self._class(
                dotation=dotation, perimetre=perimetre, created_by=request.user
            )
        response = super().dispatch(request, *args, **kwargs)
        return response

    def done(self, form_list, **kwargs):
        instance: ModeleDocument = self.instance
        is_creating = instance.pk is None

        for form in form_list:
            for key, value in form.cleaned_data.items():
                instance.__setattr__(key, value)
                if key == "logo":
                    self._handle_logo(instance, value)

        instance.save()

        self._set_success_message(instance)

        if is_creating:
            queue_matomo_event(
                self.request,
                MATOMO_CATEGORY_MODELE,
                MATOMO_ACTION_CREATION_MODELE,
                f"{self.modele_type} - {self.dotation}",
            )

        return HttpResponseRedirect(
            reverse(
                "gsl_notification:modele-liste",
                kwargs={"dotation": self.dotation},
            )
        )

    def _handle_logo(self, instance, logo):
        pass

    def _set_success_message(self, instance, verbe="créé", extra_tags="success"):
        messages.success(
            self.request,
            f'Le {instance.verbose_name()} "{instance.name}" a bien été {verbe}.',
            extra_tags=extra_tags,
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
                "modele_verbose_name": self._class.verbose_name(),
                "dotation": self.dotation,
                "current_tab": self.dotation,
                "title": self._get_form_title(),
            }
        )

        step_titles = {
            "0": "Titre du modèle",
            "1": "En-tête du modèle",
            "2": f"Contenu du {self._class.verbose_name()} pour le publipostage",
        }

        context.update(
            {
                "step_title": step_titles.get(self.steps.current, ""),
                "next_step_title": step_titles.get(self.steps.next, ""),
                "mention_items": [
                    {"id": mention.key, "label": mention.label} for mention in MENTIONS
                ],
            }
        )
        return context

    def get_template_names(self):
        return f"gsl_notification/modele/modele_form_step_{self.steps.current}.html"

    def _get_form_title(self):
        return f"Création d’un nouveau {self._class.verbose_name()} {self.dotation}"


class UpdateModele(CreateModelDocumentWizard):
    @method_decorator(csp_update({"style-src": [CSP.SELF, CSP.UNSAFE_INLINE]}))
    def dispatch(
        self,
        request,
        modele_type,
        modele_id,
        instanciate_new_modele=False,
        *args,
        **kwargs,
    ):
        self._class = MODELES[modele_type]
        self.instance = get_object_or_404(
            self._class,
            id=modele_id,
        )
        dotation = self.instance.dotation
        self.possible_modele_perimetres = get_modele_perimetres(
            dotation, request.user.perimetre
        )
        if self.instance.perimetre not in self.possible_modele_perimetres:
            raise Http404(user_message="Modèle non existant")

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

    def _set_success_message(self, instance, verbe="modifié", extra_tags=""):
        super()._set_success_message(instance, verbe, extra_tags=extra_tags)


class DuplicateModele(UpdateModele):
    @method_decorator(csp_update({"style-src": [CSP.SELF, CSP.UNSAFE_INLINE]}))
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
        super()._set_success_message(instance, verbe="créé", extra_tags="success")


class DeleteModeleView(DeleteView):
    http_method_names = ["post"]
    pk_url_kwarg = "modele_id"

    def get_queryset(self):
        _class = MODELES[self.kwargs["modele_type"]]
        user = self.request.user
        if user.is_staff:
            return _class.objects.all()

        q = Q()
        for dotation in DOTATIONS:
            try:
                perimetres = get_modele_perimetres(dotation, user.perimetre)
                q |= Q(dotation=dotation, perimetre__in=perimetres)
            except ValueError:
                pass
        return _class.objects.filter(q)

    def get_success_url(self):
        return reverse(
            "gsl_notification:modele-liste", kwargs={"dotation": self.object.dotation}
        )

    def form_valid(self, form):
        name = self.object.name

        try:
            response = super().form_valid(form)
        except ProtectedError as err:
            _add_error_message(self.request, err.protected_objects)
            return redirect(self.get_success_url())

        messages.info(
            self.request,
            f"Le {self.object.verbose_name().lower()} “{name}” a été supprimé.",
            extra_tags="delete_modele_arrete",
        )
        return response


@require_GET
def get_generic_modele(request, dotation):
    if dotation == DOTATION_DETR:
        return render(request, "gsl_notification/modele/generique/detr_modele.html")
    elif dotation == DOTATION_DSIL:
        return render(request, "gsl_notification/modele/generique/dsil_modele.html")
    raise Http404(user_message="Dotation inconnue")


def _add_error_message(request, protected_objects):
    count = len(protected_objects)
    instance = list(protected_objects)[0]
    message = (
        "Le modèle n'a pas été supprimé car il est utilisé "
        f"par {count} {instance.verbose_name(count).lower()}."
    )

    messages.error(
        request,
        message,
        extra_tags="alert",
    )

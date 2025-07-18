import os

import boto3
from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.core.files.storage import FileSystemStorage
from django.http import Http404, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods
from django.views.generic import ListView
from django_weasyprint.views import WeasyTemplateResponse
from formtools.wizard.views import SessionWizardView

from gsl import settings
from gsl_core.models import Perimetre
from gsl_notification.forms import (
    ArreteForm,
    ArreteSigneForm,
    ModeleArreteStepOneForm,
    ModeleArreteStepThreeForm,
    ModeleArreteStepTwoForm,
)
from gsl_notification.models import Arrete, ArreteSigne, ModeleArrete
from gsl_notification.utils import (
    MENTION_TO_ATTRIBUTES,
    get_modele_perimetres,
    replace_mentions_in_html,
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

    try:
        arrete = programmation_projet.arrete
        context["arrete"] = programmation_projet.arrete
        context["arrete_modal_title"] = (
            f"Suppression de l'arrêté {arrete.name} créé avec Turgot"
        )
    except Arrete.DoesNotExist:
        pass

    try:
        arrete_signe = programmation_projet.arrete_signe
        context["arrete_signe"] = arrete_signe
        context["arrete_signe_modal_title"] = (
            f"Suppression de l'arrêté {arrete_signe.name} créé par {arrete_signe.created_by}"
        )

    except ArreteSigne.DoesNotExist:
        pass

    context.update(
        {
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


# Edition form for arrêté --------------------------------------------------------------
@require_http_methods(["GET"])
@programmation_projet_visible_by_user
def select_modele(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    is_creating = not hasattr(programmation_projet, "arrete")
    page_title = (
        f"{'Création' if is_creating else 'Modification'} de l'arrêté attributif"
    )
    dotation = programmation_projet.dotation_projet.dotation
    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modeles = ModeleArrete.objects.filter(dotation=dotation, perimetre__in=perimetres)

    context = {
        "programmation_projet": programmation_projet,
        "page_title": page_title,
        "modeles_list": [
            {
                "name": obj.name,
                "description": obj.description,
                "actions": [
                    {
                        "label": "Sélectionner",
                        "href": f"{
                            reverse(
                                'notification:modifier-arrete',
                                kwargs={
                                    'programmation_projet_id': programmation_projet.id
                                },
                            )
                        }?modele_id={obj.id}",
                    },
                ],
            }
            for obj in modeles
        ],
    }
    return render(request, "gsl_notification/select_modele.html", context=context)


@csp_update({"style-src": [SELF, UNSAFE_INLINE]})
@require_http_methods(["GET", "POST"])
@programmation_projet_visible_by_user
def change_arrete_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    modele = None

    if hasattr(programmation_projet, "arrete"):
        arrete = programmation_projet.arrete
        modele = arrete.modele
        title = "Modification de l'arrêté attributif"
    else:
        arrete = Arrete()
        title = "Création de l'arrêté attributif"

    if request.GET.get("modele_id"):
        dotation = programmation_projet.dotation_projet.dotation
        perimetres = get_modele_perimetres(dotation, request.user.perimetre)
        modele = get_object_or_404(
            ModeleArrete,
            id=request.GET.get("modele_id"),
            dotation=dotation,
            perimetre__in=perimetres,
        )
        arrete.content = replace_mentions_in_html(modele.content, programmation_projet)

    if modele is None:
        raise Http404("Il n'y a pas de modèle sélectionné.")

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
        "modele": modele,
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


# Suppression d'arrêté signé ----------------------------------------------------------


@arrete_signe_visible_by_user
@require_http_methods(["POST"])
def delete_arrete_signe_view(request, arrete_signe_id):
    arrete_signe = get_object_or_404(ArreteSigne, id=arrete_signe_id)
    programmation_projet_id = arrete_signe.programmation_projet.id

    arrete_signe.delete()

    return _redirect_to_documents_view(request, programmation_projet_id)


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


class ModeleArreteListView(ListView):
    template_name = "gsl_notification/modele_arrete/list.html"

    def get_queryset(self):
        return ModeleArrete.objects.filter(
            dotation=self.dotation, perimetre__in=self.perimetres
        )

    def dispatch(self, request, dotation, *args, **kwargs):
        if dotation not in DOTATIONS:
            return Http404("Dotation inconnue")
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
                        "name": obj.name,
                        "description": obj.description,
                        "actions": [
                            {"label": "Modifier le modèle", "href": "#"},
                            {
                                "label": "Dupliquer le modèle",
                                "href": "#",
                                "class": "fr-btn--secondary",
                            },
                            {
                                "label": "Supprimer",
                                "href": "#",
                                "class": "fr-btn--tertiary",
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
        return user_perimetre

    def done(self, form_list, **kwargs):
        instance: ModeleArrete = self.instance

        for form in form_list:
            for key, value in form.cleaned_data.items():
                instance.__setattr__(key, value)

        instance.save()

        return HttpResponseRedirect(
            reverse(
                "gsl_notification:modele-arrete-liste",
                kwargs={"dotation": self.dotation},
            )
        )

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
                "mention_items": [
                    {"id": id, "label": MENTION_TO_ATTRIBUTES[id]["label"]}
                    for id in MENTION_TO_ATTRIBUTES.keys()
                ],
            }
        )
        return context

    def get_template_names(self):
        return f"gsl_notification/modele_arrete/modelearrete_form_step_{self.steps.current}.html"

import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import UpdateView
from django.views.generic.detail import SingleObjectMixin

from .exceptions import DsServiceException
from .forms import DossierReporteSansPieceForm
from .importer.dossier import save_one_dossier_from_ds
from .models import Demarche, Dossier

logger = logging.getLogger(__name__)


class RefreshOneDossierView(SingleObjectMixin, View):
    http_method_names = ["post"]
    model = Dossier
    slug_url_kwarg = "dossier_ds_number"
    slug_field = "ds_number"

    def get_queryset(self):
        return Dossier.objects.for_user(self.request.user)

    def post(self, request, dossier_ds_number):
        dossier = self.get_object()

        try:
            level, message = save_one_dossier_from_ds(dossier)
            messages.add_message(request, level, message)
        except DsServiceException:
            messages.error(
                request,
                (
                    "Une erreur s’est produite lors de l’appel à Démarche Numérique. "
                    "Essayez à nouveau dans quelques instants."
                ),
            )

        url = request.POST.get("next")
        if not url:
            url = request.headers.get("Referer")

        is_url_safe = url_has_allowed_host_and_scheme(
            url, allowed_hosts=request.get_host()
        )
        if is_url_safe:
            return redirect(url)

        return redirect("/")


@staff_member_required
def view_demarche_json(request, demarche_ds_number):
    demarche = get_object_or_404(Demarche, ds_number=demarche_ds_number)
    return JsonResponse(demarche.raw_ds_data or {})


@staff_member_required
def view_dossier_json(request, dossier_ds_number):
    dossier = get_object_or_404(Dossier, ds_number=dossier_ds_number)
    return JsonResponse(
        dossier.ds_data.raw_data
        if (dossier.ds_data and dossier.ds_data.raw_data)
        else {}
    )


class DossierSansPieceUpdateView(UpdateView):
    model = Dossier
    form_class = DossierReporteSansPieceForm
    template_name = "gsl_demarches_simplifiees/dossier_sans_piece_update.html"

    def get_success_url(self):
        messages.success(
            self.request,
            "Les informations du dossier ont été mises à jour avec succès.",
        )
        return reverse("gsl_projet:get-projet", args=[self.object.projet.pk])

    def get_queryset(self):
        return Dossier.objects.for_user(self.request.user).sans_pieces()

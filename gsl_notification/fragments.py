from django_htmx.http import HttpResponseClientRefresh

from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_ENVOI_DN,
    MATOMO_CATEGORY_NOTIFICATION,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_notification.forms import (
    GenerateDotationsDocumentsForm,
    NotificationMessageForm,
)
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.fragments import ProjetActionsFragment, ProjetFragment
from gsl_projet.models import Projet

NOTIFICATION_RESULT_TO_MATOMO_ACTION = {
    PROJET_STATUS_ACCEPTED: "accepte",
    PROJET_STATUS_REFUSED: "refuse",
    PROJET_STATUS_DISMISSED: "classe_sans_suite",
}


class NotifiedFragment(ProjetFragment):
    name = "notified"
    template_name = (
        "gsl_notification/tab_simulation_projet/tab_notifications.html#notified"
    )


class GenerateDocumentsFragment(ProjetFragment):
    name = "generate_documents"
    route_params = "<int:pk>"
    template_name = "includes/_generate_documents_form.html"
    form_class = GenerateDotationsDocumentsForm

    @classmethod
    def get_queryset(cls, request):
        return (
            Projet.objects.active()
            .for_user(request.user)
            .with_at_least_one_treated_dotation()
            .filter(notified_at__isnull=True)
        )

    def get_form(self, data=None):
        return self.form_class(projet=self.object, user=self.request.user, data=data)

    def on_valid(self):
        self.form.save()
        return HttpResponseClientRefresh()

    def on_invalid(self):
        self.form.set_autofocus_on_first_error()
        return super().on_invalid()


class NotificationMessageFragment(ProjetFragment):
    name = "notification_message"
    route_params = "<int:pk>"
    template_name = "includes/_notification_message_form.html"
    form_class = NotificationMessageForm
    oob_fragments = (NotifiedFragment, ProjetActionsFragment, GenerateDocumentsFragment)

    @classmethod
    def get_queryset(cls, request):
        return Projet.objects.active().for_user(request.user).to_notify()

    def get_context(self):
        return {
            **super().get_context(),
            "is_instructor": self.object.dossier_ds.is_instructeur(self.request.user),
            "dotation_projets_without_signed_document": list(
                self.object.dotationprojet_set.without_signed_document()
            ),
        }

    def on_valid(self):
        try:
            self.form.save(user=self.request.user)
        except DsServiceException as e:
            self.form.add_error(
                None,
                f"Une erreur est survenue lors de l'envoi de la notification. {e}",
            )
            return self.on_invalid()

        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_NOTIFICATION,
            MATOMO_ACTION_ENVOI_DN,
            NOTIFICATION_RESULT_TO_MATOMO_ACTION[self.object.status],
        )
        return self.render_valid()

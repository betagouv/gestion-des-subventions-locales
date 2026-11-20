from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import DetailView
from formtools.wizard.views import SessionWizardView

from dn.sync.models import Dotation
from gsl.core.decorators import htmx_only
from gsl.core.exceptions import Http404
from gsl.core.matomo import queue_matomo_event
from gsl.core.matomo_constants import (
    MATOMO_ACTION_ENVOI_DN,
    MATOMO_CATEGORY_NOTIFICATION,
)
from gsl.core.models import BulkActionsJob
from gsl.notification.forms.bulk_notification import (
    NotifyRefusLaunchForm,
    NotifyRefusMessageForm,
)
from gsl.notification.tasks import run_bulk_notification_refus_job
from gsl.notification.views.generate_document_for_multiple_projets_views import (
    HtmxModalWizardMixin,
    Step,
)
from gsl.programmation.constants import BulkAction

MODAL_ID = "notify-refus-modal"
MODAL_TITLE = "Notifier les refus et classements sans suite"
TEMPLATES = "gsl_notification/modal/bulk_notification/"
PROGRESS_TEMPLATE = TEMPLATES + "progress_step.html"

# The launch step is the trigger button submission, from the projet list page.
# It is only ever rendered when resolving the checked projets fails.
LAUNCH = Step(
    name="launch",
    form_class=NotifyRefusLaunchForm,
    template="gsl_notification/modal/bulk_generation/launch.html",
    form_kwargs=("user", "dotation"),
)
MESSAGE = Step(
    name="message",
    form_class=NotifyRefusMessageForm,
    template=TEMPLATES + "message_step.html",
    title="Message de notification",
    form_kwargs=("user",),
    extra_context=("enveloppe_projets",),
)


class DotationMixin:
    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("dotation") not in Dotation.values:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    @property
    def dotation(self) -> str:
        return self.kwargs["dotation"]


@method_decorator(htmx_only, name="dispatch")
class NotifyRefusWizard(DotationMixin, HtmxModalWizardMixin, SessionWizardView):
    """
    Notifies DN of the refusal or dismissal of the checked projets, all with
    the same message, then polls the BulkActionsJob until every projet is done.
    """

    STEPS = (LAUNCH, MESSAGE)

    MODAL_TITLE = MODAL_TITLE
    MODAL_POST_URL_NAME = "gsl_notification:notify-refus-modal"
    modal_id = MODAL_ID

    def get_storage_namespace(self):
        # One run per dotation, so DETR and DSIL don't collide.
        return self.dotation

    @property
    def user(self):
        return self.request.user

    @property
    def enveloppe_projets(self):
        launch_data = self.get_cleaned_data_for_step(LAUNCH.name) or {}
        return launch_data.get("ids") or []

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context["dotation"] = self.dotation
        return context

    def done(self, form_list, form_dict, **kwargs):
        enveloppe_projets = form_dict[LAUNCH.name].cleaned_data["ids"]
        job = form_dict[MESSAGE.name].save(enveloppe_projets)
        run_bulk_notification_refus_job.delay(str(job.pk))
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_NOTIFICATION,
            MATOMO_ACTION_ENVOI_DN,
            f"refus_en_masse:{job.total}",
        )
        context = {
            "job": job,
            "dotation": self.dotation,
            "modal_id": MODAL_ID,
            "modal_title": MODAL_TITLE,
        }
        return render(self.request, PROGRESS_TEMPLATE, context)


@method_decorator(htmx_only, name="dispatch")
class NotifyRefusProgressView(DotationMixin, DetailView):
    """Polled while the job is running, then renders its report."""

    model = BulkActionsJob
    template_name = PROGRESS_TEMPLATE
    context_object_name = "job"

    def get_queryset(self):
        return BulkActionsJob.objects.filter(
            action=BulkAction.NOTIFY_REFUS, created_by=self.request.user
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "dotation": self.dotation,
                "modal_id": MODAL_ID,
                "modal_title": MODAL_TITLE,
            }
        )
        return context

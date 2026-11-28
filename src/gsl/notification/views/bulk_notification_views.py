from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import DetailView
from django_htmx.http import trigger_client_event
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
    NotifyAcceptedLaunchForm,
    NotifyMessageForm,
    NotifyRefusLaunchForm,
)
from gsl.notification.tasks import run_bulk_notification_job
from gsl.notification.views.generate_document_for_multiple_projets_views import (
    HtmxModalWizardMixin,
    Step,
)

TEMPLATES = "gsl_notification/modal/bulk_notification/"
LAUNCH_TEMPLATE = "gsl_notification/modal/bulk_generation/launch.html"
PROGRESS_TEMPLATE = TEMPLATES + "progress_step.html"
LAUNCH_FORM_KWARGS = ("user", "dotation")


MESSAGE = Step(
    name="message",
    form_class=NotifyMessageForm,
    template=TEMPLATES + "message_step.html",
    title="Message de notification",
    form_kwargs=("user", "action"),
    extra_context=("enveloppe_projets", "skipped_count", "decision_label"),
)


class DotationMixin:
    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("dotation") not in Dotation.values:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    @property
    def dotation(self) -> str:
        return self.kwargs["dotation"]


class BaseNotifyWizard(HtmxModalWizardMixin, SessionWizardView):
    """
    Notifies DN of the decision on the checked projets, all with the same
    message, then polls the BulkActionsJob until every projet is done.

    The launch step is the trigger button submission, from the projet list
    page. It is only ever rendered when resolving the checked projets fails.
    """

    MATOMO_LABEL: str

    @property
    def dotation(self) -> str:
        return self.kwargs["dotation"]

    def get_storage_namespace(self):
        # One run per dotation, so DETR and DSIL don't collide.
        return self.dotation

    @property
    def user(self):
        return self.request.user

    @property
    def launch_data(self) -> dict:
        return self.get_cleaned_data_for_step(self.steps.first) or {}

    @property
    def enveloppe_projets(self):
        return self.launch_data.get("ids") or []

    @property
    def skipped_count(self) -> int:
        return self.launch_data.get("skipped_count", 0)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context["dotation"] = self.dotation
        return context

    def done(self, form_list, form_dict, **kwargs):
        launch_form, message_form = form_list
        job = message_form.save(launch_form.cleaned_data["ids"])
        run_bulk_notification_job.delay(str(job.pk))
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_NOTIFICATION,
            MATOMO_ACTION_ENVOI_DN,
            f"{self.MATOMO_LABEL}:{job.total}",
        )
        context = {
            "job": job,
            "dotation": self.dotation,
            "modal_id": self.modal_id,
            "modal_title": self.MODAL_TITLE,
        }
        return render(self.request, PROGRESS_TEMPLATE, context)


class NotifyRefusWizard(BaseNotifyWizard):
    STEPS = (
        Step(
            "launch",
            NotifyRefusLaunchForm,
            LAUNCH_TEMPLATE,
            form_kwargs=LAUNCH_FORM_KWARGS,
        ),
        MESSAGE,
    )
    MODAL_TITLE = "Notifier les refus et classements sans suite"
    MATOMO_LABEL = "refus_en_masse"
    modal_id = "notify-refus-modal"
    decision_label = "refusé(s) ou classé(s) sans suite"


class NotifyAcceptedWizard(BaseNotifyWizard):
    STEPS = (
        Step(
            "launch",
            NotifyAcceptedLaunchForm,
            LAUNCH_TEMPLATE,
            form_kwargs=LAUNCH_FORM_KWARGS,
        ),
        MESSAGE,
    )
    MODAL_TITLE = "Notifier les acceptations"
    MATOMO_LABEL = "acceptation_en_masse"
    modal_id = "notify-accepted-modal"
    decision_label = "accepté(s)"


WIZARDS_BY_ACTION = {
    wizard.action: wizard for wizard in (NotifyRefusWizard, NotifyAcceptedWizard)
}


@method_decorator(htmx_only, name="dispatch")
class NotifyProgressView(DotationMixin, DetailView):
    """Polled while the job is running, then renders its report."""

    model = BulkActionsJob
    template_name = PROGRESS_TEMPLATE
    context_object_name = "job"

    def get_queryset(self):
        return BulkActionsJob.objects.filter(
            action__in=WIZARDS_BY_ACTION, created_by=self.request.user
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard = WIZARDS_BY_ACTION[self.object.action]
        context.update(
            {
                "dotation": self.dotation,
                "modal_id": wizard.modal_id,
                "modal_title": wizard.MODAL_TITLE,
            }
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        if self.object.is_unfinished:
            return response
        return trigger_client_event(response, BulkActionsJob.DONE_EVENT)

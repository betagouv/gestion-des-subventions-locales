from django.http import HttpResponse, HttpResponseBadRequest
from django_htmx.http import trigger_client_event


class OpenHtmxModalMixin:
    """
    Mixin to automatically open a DSFR modal after it has been swapped in the DOM by htmx.
    """

    modal_id = None

    def get_modal_id(self):
        return self.modal_id

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modal_id"] = self.get_modal_id()
        context["modal_button_id"] = f"{self.get_modal_id()}-button"
        return context

    def render_to_response(self, context, *args, **kwargs):
        return trigger_client_event(
            super().render_to_response(context, *args, **kwargs),
            "click",
            {"target": f"#{self.get_modal_id()}-button"},
            after="settle",
        )


class NoFeedbackHtmxFormViewMixin:
    """
    A view to handle forms submitted via htmx, which provides no feedback to the user.
    Can be combined with any FormView (basic FormView, UpdateView, CreateView, etc.)

    It returns :
    * a 204 No Content response if the save is successful
    * a 400 Bad Request response if the form is invalid

    It should only be used for "API type" form submissions
    when an invalid form is never expected. The 400 case
    should not happen and be handled client-side as an unexpected bug.

    The typical HTML on the client side would be
    <form
        hx-post="<this view url>"
        hx-swap="none"
    >
        <only select or checkbox fields which cannot be invalid>
    </form>
    """

    def form_valid(self, form):
        form.save()
        return HttpResponse(status=204)

    def form_invalid(self, form):
        return HttpResponseBadRequest(form.errors.as_json())

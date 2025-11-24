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

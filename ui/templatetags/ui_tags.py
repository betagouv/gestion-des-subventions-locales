from django import template
from dsfr.utils import parse_tag_args

register = template.Library()


@register.inclusion_tag("ui/components/confirmation_modal.html")
def ui_confirmation_modal(*args, **kwargs) -> dict:
    """
    ```python
    data_dict = {
        "modal_id": "The unique html id of the dialog",
        "title": "Title of the modal",
        "text": "Text content",
        "action_text": "(Optional) Text of the confirmation button, 'Confirmer' by default",
        "form": "(Optional) Reference to the form id. If defined, the confirmation button type will be 'submit'",
    }
    ```"""
    allowed_keys = ["modal_id", "title", "text", "form", "action_text"]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)

    return {"self": tag_data}

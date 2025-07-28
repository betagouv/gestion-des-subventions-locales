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
        "icon": "(Optional) Icon at the title left. 'fr-icon-delete-fill' by default",
        "class": "(Optional) Icon at the title left. 'fr-icon-delete-fill' by default",
        "is_title_red": "(Optional) Give to the title a red color. True by default"
    }
    ```"""
    allowed_keys = [
        "modal_id",
        "title",
        "text",
        "form",
        "action_text",
        "icon",
        "is_title_red",
    ]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)
    if "is_title_red" not in tag_data:
        tag_data["is_title_red"] = True

    return {"self": tag_data}


@register.inclusion_tag("ui/components/tiptap_editor.html")
def ui_tiptap_editor(*args, **kwargs) -> dict:
    """
    ```python
    data_dict = {
        "with_mention": "(Optional) Useful if we want mentions triggered by @. False by default",
        "mentions": "(Optionnal) Used if `with_mention` is True",
    }
    ```"""
    allowed_keys = ["with_mention", "mentions"]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)
    if "with_mention" not in tag_data:
        tag_data["with_mention"] = False
        tag_data["mentions"] = []

    return {"self": tag_data}

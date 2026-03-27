import json

from django import template
from dsfr.utils import parse_tag_args

register = template.Library()


@register.inclusion_tag("ui/components/multiselect.html")
def ui_multiselect(*args, **kwargs) -> dict:
    """
    ```python
    data_dict = {
        "id": "The field id",
        "field": "Multiple Choice Filter field form",
        "label": "Field label",
        "default_placeholder": "Placeholder when nothing is selected",
    }
    ```"""
    allowed_keys = [
        "id",
        "field",
        "label",
        "default_placeholder",
    ]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)

    field = tag_data["field"]
    selected = field.data or []
    tag_data["is_active"] = bool(selected)

    if selected:
        choices_dict = dict(field.field.choices)
        tag_data["placeholder"] = ", ".join(
            str(choices_dict[v]) for v in selected if v in choices_dict
        )
    else:
        tag_data["placeholder"] = tag_data.get("default_placeholder", "")

    return {"self": tag_data}


@register.simple_tag
def range_field_context(bound_field):
    return bound_field.field.widget.get_decomposed_context(bound_field)


@register.simple_tag
def filter_placeholder(bound_field):
    widget = bound_field.field.widget
    if widget.placeholder:
        return widget.placeholder
    selected = bound_field.data or []
    choices = bound_field.field.choices
    if selected:
        choices_dict = {str(k): v for k, v in choices}
        placeholder = ", ".join(
            str(choices_dict[str(v)]) for v in selected if str(v) in choices_dict
        )
        if placeholder:
            return placeholder
    if choices:
        return str(choices[0][1])
    return ""


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
        "content_field_name": "Name of the content input field which will contain the data to store",
        "with_mention": "(Optional) Useful if we want mentions triggered by @. False by default",
        "mentions": "(Optionnal) Used if `with_mention` is True",
    }
    ```"""
    allowed_keys = ["content_field_name", "with_mention", "mentions"]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)
    if "with_mention" not in tag_data:
        tag_data["with_mention"] = False
        tag_data["mentions"] = []

    if "mentions" in tag_data:
        tag_data["json_mention_items"] = json.dumps(tag_data["mentions"])

    return {"self": tag_data}

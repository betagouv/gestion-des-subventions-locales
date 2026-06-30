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
        choices_dict = {str(k): v for k, v in field.field.choices}
        tag_data["placeholder"] = ", ".join(
            str(choices_dict[str(v)]) for v in selected if str(v) in choices_dict
        ) or tag_data.get("default_placeholder", "")
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


_STATUS_BADGE_CONFIGS = {
    "accepted": {
        "icon_class": "fr-icon-checkbox-circle-fill",
        "label": "Accepté",
        "badge_class": "badge-projet-status__accepted",
    },
    "refused": {
        "icon_class": "fr-icon-close-circle-fill",
        "label": "Refusé",
        "badge_class": "badge-projet-status__refused",
    },
    "dismissed": {
        "icon_class": "fr-icon-close-circle-fill",
        "label": "Classé sans suite",
        "badge_class": "badge-projet-status__dismissed",
    },
    "reported": {
        "icon_class": "fr-icon-arrow-turn-back-line fr-icon--sm fr-mr-1v",
        "label": "Reporté",
        "badge_class": "fr-badge--green-menthe",
    },
    "processing": {
        "label": "En traitement",
    },
}


@register.inclusion_tag("ui/components/status_badge.html")
def ui_status_badge(*args, **kwargs) -> dict:
    """
    ```python
    data_dict = {
        "type": "accepted | refused | dismissed | reported",
        "dotation": "(Optional) Dotation prefix, e.g. 'DETR' or 'DSIL'",
        "class": "(Optional) Extra CSS classes on the <span>",
    }
    ```"""
    allowed_keys = ["type", "dotation", "class"]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)

    config = _STATUS_BADGE_CONFIGS.get(tag_data.get("type", ""), {})
    label = config.get("label", "")
    if tag_data.get("dotation"):
        label = f"{tag_data['dotation']} {label}"

    return {
        "self": {
            "badge_class": config.get("badge_class", ""),
            "icon_class": config.get("icon_class", ""),
            "label": label,
            "extra_class": tag_data.get("class", ""),
        }
    }


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

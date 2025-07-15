from django import template
from dsfr.utils import parse_tag_args

register = template.Library()


@register.inclusion_tag("ui/components/confirmation_modal.html")
def ui_confirmation_modal(*args, **kwargs) -> dict:
    allowed_keys = ["modal_id", "title", "text", "form"]
    tag_data = parse_tag_args(args, kwargs, allowed_keys)

    return {"self": tag_data}

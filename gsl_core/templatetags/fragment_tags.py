from django import template
from django.utils.safestring import mark_safe

from gsl_core.fragments import Fragment

register = template.Library()


@register.simple_tag(takes_context=True)
def render_fragment(context, key, obj):
    fragment_cls = Fragment.get(key)
    return mark_safe(fragment_cls(context["request"], obj).render())

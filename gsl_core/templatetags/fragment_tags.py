from django import template
from django.utils.safestring import mark_safe

from gsl_core.fragments import Fragment

register = template.Library()


@register.simple_tag(takes_context=True)
def render_fragment(context, key, obj):
    fragment_cls = Fragment.get(key)
    return mark_safe(fragment_cls(context["request"], obj).render())


def register_fragment_tag(name):
    """Derive an inclusion tag from an HTMX view"""

    def decorator(view_cls):
        @register.inclusion_tag(view_cls.template_name, takes_context=True, name=name)
        def _tag(context, instance):
            view = view_cls()
            view.setup(context["request"])
            view.object = instance
            return view.get_context_data()

        return view_cls

    return decorator

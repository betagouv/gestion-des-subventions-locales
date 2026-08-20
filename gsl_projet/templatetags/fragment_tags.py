from django import template

register = template.Library()


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

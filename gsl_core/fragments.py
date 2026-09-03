from collections import defaultdict
from http import HTTPMethod

from django.apps import apps
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import include, path
from django.utils.functional import classproperty

from gsl_core.decorators import htmx_only


class Fragment:
    """
    A self-contained page fragment: its partial template, the context that
    partial needs, and — for htmx form fragments — the sibling fragments it
    refreshes out-of-band on success.

    The same class serves two modes:
      - {% render_fragment "<app>:<name>" obj %} to render it inside a page;
      - <FragmentClass>.as_view() as an htmx endpoint.

    A successful POST re-renders the fragment plus every fragment listed in
    `oob_fragments`, each swapped out-of-band, so the response carries only the
    blocks that changed instead of a whole re-rendered page. Siblings receive
    the already-loaded object, so they render from the same subject without
    re-running their own (endpoint) `get_queryset`.

    Any subclass that sets `name` registers itself for {% render_fragment %}.
    """

    registry = defaultdict(dict)  # {app_label: {name: cls}}

    name = None
    route_params = None
    template_name = None
    form_class = None
    oob_fragments = ()
    context_object_name = "object"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.allowed_methods = [m for m in HTTPMethod if hasattr(cls, f"on_{m.lower()}")]
        if cls.name:
            Fragment.registry[cls.app_label][cls.name] = cls

    @classproperty
    def app_label(cls):
        return apps.get_containing_app_config(cls.__module__).label

    @classmethod
    def get(cls, key):
        app_label, name = key.split(":", 1)
        return Fragment.registry[app_label][name]

    def __init__(self, request, obj):
        self.request = request
        self.object = obj
        self.form = None

    @classmethod
    def get_queryset(cls, request):
        raise NotImplementedError

    def get_context(self):
        return {self.context_object_name: self.object}

    def get_form(self, data=None):
        return self.form_class(instance=self.object, data=data)

    def render(self, *, oob=False, **extra):
        form = self.form
        if form is None and self.form_class:
            form = self.get_form()
        context = {**self.get_context(), "oob": oob, **extra}
        if form is not None:
            context["form"] = form
        return render_to_string(self.template_name, context, request=self.request)

    def render_valid(self, **extra):
        html = self.render(**extra)
        html += "".join(
            fragment(self.request, self.object).render(oob=True)
            for fragment in self.oob_fragments
        )
        return HttpResponse(html)

    def render_invalid(self):
        return HttpResponse(self.render())

    def on_valid(self):
        self.form.save()
        return self.render_valid()

    def on_invalid(self):
        # The call will fail if there are only non-fields errors.
        if any(bound_field.errors for bound_field in self.form):
            self.form.set_autofocus_on_first_error()
        return self.render_invalid()

    def on_post(self):
        self.form = self.get_form(data=self.request.POST)
        if self.form.is_valid():
            return self.on_valid()
        return self.on_invalid()

    @classmethod
    def get_object(cls, request, **kwargs):
        return get_object_or_404(cls.get_queryset(request), **kwargs)

    @classmethod
    def as_view(cls):
        @htmx_only
        def view(request, **kwargs):
            if request.method not in cls.allowed_methods:
                return HttpResponseNotAllowed(cls.allowed_methods)
            fragment = cls(request, cls.get_object(request, **kwargs))
            return getattr(fragment, f"on_{request.method.lower()}")()

        return view

    @classmethod
    def as_url(cls):
        return path(f"{cls.name}/{cls.route_params}/", cls.as_view(), name=cls.name)


def fragment_urlpatterns():
    """Every registered fragment that declares `route_params` becomes an
    endpoint under `fragment/<app>/`, its path derived from `name`. Mount once
    at the project root; url names are `fragment:<app>:<name>`."""
    includes = []
    for app_label, fragments in Fragment.registry.items():
        patterns = [f.as_url() for f in fragments.values() if f.route_params]
        if patterns:
            includes.append(path(f"{app_label}/", include((patterns, app_label))))
    return path("fragment/", include((includes, "fragment")))

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from urllib.parse import urlsplit

from django.http import Http404
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import RedirectView

CAMPAGNES = (2026, 2027)

_active: ContextVar[int | None] = ContextVar("campagne", default=None)


def default_campagne() -> int:
    return date.today().year


def get_campagne() -> int:
    return _active.get() or default_campagne()


def activate(campagne: int) -> None:
    _active.set(campagne)


@contextmanager
def active_campagne(campagne: int | None = None):
    token = _active.set(campagne)
    try:
        yield
    finally:
        _active.reset(token)


class DefaultCampagneRedirectView(RedirectView):
    """Keeps the campagne-less bookmarks of the agents working."""

    permanent = False
    query_string = True

    def get_redirect_url(self, *args, **kwargs):
        return super().get_redirect_url(*args, campagne=get_campagne(), **kwargs)


class ChangeCampagneView(RedirectView):
    """
    Switch to another campagne (remembered in session by the CampagneMiddleware),
    staying on the page the agent comes from.
    """

    permanent = False

    def get_redirect_url(self, *args, campagne, **kwargs):
        if campagne not in CAMPAGNES:
            raise Http404
        next_url = self.request.GET.get("next", "")
        if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return reverse("projet:list", kwargs={"campagne": campagne})
        return _swap_campagne_in_url(next_url, campagne)


def _swap_campagne_in_url(url: str, campagne: int) -> str:
    try:
        match = resolve(urlsplit(url).path)
    except Resolver404:
        return url
    if "campagne" not in match.kwargs:
        return url
    # Filters may not make sense in the other campagne: drop the querystring.
    return reverse(match.view_name, kwargs={**match.kwargs, "campagne": campagne})

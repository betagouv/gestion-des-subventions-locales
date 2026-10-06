from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date

from django.views.generic import RedirectView

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

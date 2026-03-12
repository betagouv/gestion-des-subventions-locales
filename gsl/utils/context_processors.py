from django.conf import settings


def export_vars(request):
    data = {}
    data["ENV"] = settings.ENV
    data["MATOMO_SITE_ID"] = settings.MATOMO_SITE_ID
    return data


def matomo_events(request):
    # For HTMX partial requests (non-boosted), events are handled via HX-Trigger
    # header in MatomoHtmxMiddleware — skip here to avoid consuming them prematurely.
    if getattr(request, "htmx", None) and not request.htmx.boosted:
        return {"matomo_pending_events": []}
    if not hasattr(request, "session"):
        return {"matomo_pending_events": []}
    events = request.session.pop("matomo_pending_events", None)
    if events:
        request.session.modified = True
    return {"matomo_pending_events": events or []}

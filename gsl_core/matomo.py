def queue_matomo_event(request, category: str, action: str, name: str = ""):
    """
    Store a Matomo event in the session so it can be emitted on the next page render.
    Useful for HTMX views that trigger a full-page refresh (HX-Refresh),
    or for any view that redirects before the next HTML response.
    """
    events = request.session.setdefault("matomo_pending_events", [])
    events.append({"category": category, "action": action, "name": name})
    request.session.modified = True

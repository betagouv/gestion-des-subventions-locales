from django.conf import settings
from django.views.decorators.csp import csp_override


def csp_update(directives):
    """Apply csp_override with base SECURE_CSP merged with the given directives."""
    policy = dict(settings.SECURE_CSP)
    policy.update(directives)
    return csp_override(policy)

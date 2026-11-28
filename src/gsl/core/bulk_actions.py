from dn.sync.models import Dotation
from gsl.core.decorators import htmx_only
from gsl.core.exceptions import Http404

# Filled by each app's bulk_actions module, autodiscovered at startup.
WIZARDS = {}
WIZARD_VIEWS = {}


def register(*wizards):
    for wizard in wizards:
        WIZARDS[wizard.action] = wizard
        WIZARD_VIEWS[wizard.action] = wizard.as_view()


@htmx_only
def bulk_action_wizard(request, dotation, action):
    if dotation not in Dotation.values:
        raise Http404(user_message="Dotation inconnue")
    if action not in WIZARD_VIEWS:
        raise Http404(user_message="Action inconnue")
    return WIZARD_VIEWS[action](request, dotation=dotation)

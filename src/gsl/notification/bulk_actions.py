from gsl.core.bulk_actions import register
from gsl.notification.views.bulk_notification_views import (
    NotifyAcceptedWizard,
    NotifyRefusWizard,
)
from gsl.notification.views.generate_document_for_multiple_projets_views import (
    GenerateAcceptedDocumentsWizard,
    GenerateLettreRefusWizard,
)

register(
    GenerateAcceptedDocumentsWizard,
    GenerateLettreRefusWizard,
    NotifyRefusWizard,
    NotifyAcceptedWizard,
)

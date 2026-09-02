import pytest
from django.shortcuts import reverse
from django.utils import timezone

from gsl.historique.models import ProjetAction
from gsl_core.tests.factories import ClientWithLoggedUserFactory, CollegueFactory
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db()


def test_notified_action_is_displayed_above_status_change_action_with_same_created_at():
    user = CollegueFactory()
    projet = ProjetFactory(dossier_ds__perimetre=user.perimetre)
    created_at = timezone.now()

    status_change_action = ProjetAction.objects.create(
        projet=projet,
        action_type=ProjetAction.TYPE_STATUS_CHANGE,
        source=ProjetAction.SOURCE_DN,
        created_at=created_at,
    )
    notified_action = ProjetAction.objects.create(
        projet=projet,
        action_type=ProjetAction.TYPE_NOTIFIED,
        source=ProjetAction.SOURCE_DN,
        created_at=created_at,
    )

    url = reverse("gsl_projet:get-projet-historique", kwargs={"projet_id": projet.id})
    response = ClientWithLoggedUserFactory(user=user).get(url)

    assert response.status_code == 200
    actions = list(response.context["actions"])
    assert [a.pk for a in actions] == [notified_action.pk, status_change_action.pk]

"""
Tests for ``RefusedDismissedNotificationModalView`` and the
``RefusedDismissedNotificationForm`` it drives.
"""

from typing import cast
from unittest import mock

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_notification.forms import RefusedDismissedNotificationForm
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre) -> Collegue:
    return cast(Collegue, CollegueWithDSProfileFactory(perimetre=perimetre))


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


def _refused_projet(perimetre, dotation=DOTATION_DETR):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dp = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_REFUSED
    )
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    ProgrammationProjetFactory(
        dotation_projet=dp,
        enveloppe=enveloppe,
        status="refused",
    )
    return projet


def _dismissed_projet(perimetre, dotation=DOTATION_DETR):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dp = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_DISMISSED
    )
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    ProgrammationProjetFactory(
        dotation_projet=dp,
        enveloppe=enveloppe,
        status="dismissed",
    )
    return projet


class TestForm:
    def test_refused_projet_pushes_dossier_refuser_and_sets_notified_at(
        self, perimetre, collegue
    ):
        projet = _refused_projet(perimetre)
        with (
            mock.patch(
                "gsl_notification.forms.DsMutator.dossier_refuser"
            ) as mock_refuser,
            mock.patch(
                "gsl_notification.forms.DsService.dismiss_in_ds"
            ) as mock_dismiss,
        ):
            form = RefusedDismissedNotificationForm(
                data={"justification": "Refusé"},
                files={},
                instance=projet,
            )
            assert form.is_valid()
            form.save(user=collegue)
        mock_refuser.assert_called_once()
        mock_dismiss.assert_not_called()
        projet.refresh_from_db()
        assert projet.notified_at is not None

    def test_dismissed_projet_pushes_dismiss_and_sets_notified_at(
        self, perimetre, collegue
    ):
        projet = _dismissed_projet(perimetre)
        with (
            mock.patch(
                "gsl_notification.forms.DsService.dismiss_in_ds"
            ) as mock_dismiss,
            mock.patch(
                "gsl_notification.forms.DsMutator.dossier_refuser"
            ) as mock_refuser,
        ):
            form = RefusedDismissedNotificationForm(
                data={"justification": "Classé"},
                files={},
                instance=projet,
            )
            assert form.is_valid()
            form.save(user=collegue)
        mock_dismiss.assert_called_once()
        mock_refuser.assert_not_called()
        projet.refresh_from_db()
        assert projet.notified_at is not None

    def test_dismissed_double_dotation_picks_optimistic_dismiss(
        self, perimetre, collegue
    ):
        """REFUSED + DISMISSED resolves to DISMISSED (optimistic)."""
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        detr_dp = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
        )
        ProgrammationProjetFactory(
            dotation_projet=detr_dp,
            enveloppe=DetrEnveloppeFactory(perimetre=perimetre),
            status="refused",
        )
        dsil_dp = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_DISMISSED
        )
        ProgrammationProjetFactory(
            dotation_projet=dsil_dp,
            enveloppe=DsilEnveloppeFactory(perimetre=perimetre),
            status="dismissed",
        )

        with (
            mock.patch(
                "gsl_notification.forms.DsService.dismiss_in_ds"
            ) as mock_dismiss,
            mock.patch(
                "gsl_notification.forms.DsMutator.dossier_refuser"
            ) as mock_refuser,
        ):
            form = RefusedDismissedNotificationForm(
                data={"justification": "Classé"},
                files={},
                instance=projet,
            )
            assert form.is_valid()
            form.save(user=collegue)

        mock_dismiss.assert_called_once()
        mock_refuser.assert_not_called()


class TestView:
    def test_get_renders_modal(self, client_with_user_logged, perimetre):
        projet = _refused_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/refus-ou-classement/"
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert "gsl_notification/modal/notify_refused_dismissed.html" in [
            t.name for t in response.templates
        ]

    def test_get_without_trigger_name_renders_button(
        self, client_with_user_logged, perimetre
    ):
        """Default trigger (e.g. from project detail page): swap to a <button>."""
        projet = _refused_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/refus-ou-classement/"
        modal_id = f"notify-refused-dismissed-modal-{projet.id}"
        modal_button_id = f"{modal_id}-button"

        response = client_with_user_logged.get(
            url,
            headers={"HX-Request": "true", "HX-Trigger": "to_notify_button"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert '<button class="fr-mt-0 fr-btn' in content
        assert f'id="{modal_button_id}"' in content
        assert f'<dialog class="fr-modal"\n            id="{modal_id}"' in content

    def test_get_with_link_trigger_name_renders_link(
        self, client_with_user_logged, perimetre
    ):
        """Trigger from a table cell <a>: swap to a styled <a>, not a <button>."""
        projet = _refused_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/refus-ou-classement/"
        modal_id = f"notify-refused-dismissed-modal-{projet.id}"
        modal_button_id = f"{modal_id}-button"

        response = client_with_user_logged.get(
            url,
            headers={
                "HX-Request": "true",
                "HX-Trigger-Name": "notify-refused-dismissed-link",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert f'id="{modal_button_id}"' in content
        assert f'aria-controls="{modal_id}"' in content
        assert 'data-fr-opened="false"' in content
        assert "fr-link fr-link--icon-right fr-icon-mail-line" in content
        assert "À notifier" in content
        # The swapped trigger must be an <a>, not the default <button>.
        assert "fr-mt-0 fr-btn fr-btn--icon-left" not in content
        # The modal itself is still OOB-injected.
        assert f'<dialog class="fr-modal"\n            id="{modal_id}"' in content

    def test_post_pushes_to_ds_and_returns_refresh(
        self, client_with_user_logged, perimetre
    ):
        projet = _refused_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/refus-ou-classement/"
        with mock.patch(
            "gsl_notification.forms.DsMutator.dossier_refuser"
        ) as mock_refuser:
            response = client_with_user_logged.post(
                url, {"justification": "Refusé"}, headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        assert response.headers.get("HX-Refresh") == "true"
        mock_refuser.assert_called_once()
        projet.refresh_from_db()
        assert projet.notified_at is not None

    def test_view_excludes_projets_with_accepted_dotation(
        self, client_with_user_logged, perimetre
    ):
        """If any dotation is accepted, this view is not the right entry point."""
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        accepted_dp = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
        )
        ProgrammationProjetFactory(
            dotation_projet=accepted_dp,
            enveloppe=DetrEnveloppeFactory(perimetre=perimetre),
            status="accepted",
        )
        refused_dp = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_REFUSED
        )
        ProgrammationProjetFactory(
            dotation_projet=refused_dp,
            enveloppe=DsilEnveloppeFactory(perimetre=perimetre),
            status="refused",
        )

        url = f"/notification/{projet.id}/notifier/refus-ou-classement/"
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})
        assert response.status_code == 404

    def test_view_excludes_already_notified_projets(
        self, client_with_user_logged, perimetre
    ):
        from django.utils import timezone

        projet = _refused_projet(perimetre)
        projet.notified_at = timezone.now()
        projet.save()

        url = f"/notification/{projet.id}/notifier/refus-ou-classement/"
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})
        assert response.status_code == 404

"""
Tests for ``gsl_programmation/table_cells/notification.html``.

The cell must branch on ``projet.has_accepted_dotation`` for ``to_notify``
projets so that refused/dismissed projets open the HTMX modal instead of
hitting the accepted-only ``gsl_notification:documents`` view (which 404s).
"""

import pytest
from django.template.loader import render_to_string

from gsl_core.tests.factories import PerimetreDepartementalFactory
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, PROJET_STATUS_REFUSED
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def _render(programmation_projet):
    return render_to_string(
        "gsl_programmation/table_cells/notification.html",
        {"programmation_projet": programmation_projet},
    )


def test_refused_projet_renders_htmx_link_to_refused_dismissed_modal():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dp = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=dp,
        enveloppe=DetrEnveloppeFactory(perimetre=perimetre),
        status="refused",
    )

    html = _render(programmation_projet)

    assert f"/notification/{projet.id}/notifier/refus-ou-classement/" in html
    assert 'hx-get="' in html
    assert 'name="notify-refused-dismissed-link"' in html
    assert f"/notification/{projet.id}/documents/" not in html

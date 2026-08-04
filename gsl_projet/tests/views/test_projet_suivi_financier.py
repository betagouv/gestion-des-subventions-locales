from decimal import Decimal

import pytest
from django.shortcuts import reverse

from gsl_chorus.models import SuiviFinancier
from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import PROJET_STATUS_PROCESSING
from gsl_projet.tests.factories import (
    DetrProjetFactory,
    DotationProjetFactory,
    ProjetFactory,
)

pytestmark = pytest.mark.django_db()

DS_NUMBER = 28281965


def url(projet):
    return reverse(
        "gsl_projet:get-projet-suivi-financier", kwargs={"projet_id": projet.id}
    )


def test_returns_404_without_accepted_dotation():
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    DotationProjetFactory(projet=projet, status=PROJET_STATUS_PROCESSING)

    response = ClientWithLoggedUserFactory(user=user).get(url(projet))
    assert response.status_code == 404


def test_displays_chorus_lines_grouped_by_dotation():
    perimetre = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre)
    projet = ProjetFactory(
        dossier_ds__perimetre=perimetre, dossier_ds__ds_number=DS_NUMBER
    )
    ProgrammationProjetFactory(
        dotation_projet=DetrProjetFactory(projet=projet),
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=Decimal("13000"),
    )
    SuiviFinancier.objects.create(
        ej="2105003612", dn=DS_NUMBER, dotation="DETR", montant=Decimal("10000")
    )
    SuiviFinancier.objects.create(
        ej="2105003612",
        dn=DS_NUMBER,
        dotation="DETR",
        montant=Decimal("3000"),
        type_montant="0250",
    )

    response = ClientWithLoggedUserFactory(user=user).get(url(projet))
    assert response.status_code == 200

    (groupe,) = response.context["par_dotation"]
    assert groupe["dotation"] == "DETR"
    assert groupe["engage"] == Decimal("13000")
    assert groupe["paye"] == Decimal("3000")
    assert groupe["accorde"] == Decimal("13000")
    assert groupe["ecart"] is False

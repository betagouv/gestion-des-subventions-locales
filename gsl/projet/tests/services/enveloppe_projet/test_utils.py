from datetime import UTC

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl.core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_demarches_simplifiees.models import Dossier

from ....constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ....services.enveloppe_projet_services import EnveloppeProjetService
from ...factories import EnveloppeProjetFactory

synchroniser = EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet


@pytest.fixture
def perimetres():
    arr_dijon = PerimetreArrondissementFactory()
    dep_21 = PerimetreDepartementalFactory(
        departement=arr_dijon.departement, region=arr_dijon.region
    )
    region_bfc = PerimetreRegionalFactory(region=dep_21.region)

    arr_nanterre = PerimetreArrondissementFactory()
    dep_92 = PerimetreDepartementalFactory(departement=arr_nanterre.departement)
    region_idf = PerimetreRegionalFactory(region=dep_92.region)
    return [
        arr_dijon,
        dep_21,
        region_bfc,
        arr_nanterre,
        dep_92,
        region_idf,
    ]


# -- root enveloppe of a dotation treated in DN --


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_refused_dotation_goes_to_the_root_enveloppe_with_a_detr_and_arrondissement_projet(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.REFUSE,
    )
    dep_detr_enveloppe = DetrEnveloppeFactory(perimetre=dep_21, annee=2025)
    _arr_detr_enveloppe = DetrEnveloppeFactory(
        perimetre=arr_dijon, annee=2025, parent=dep_detr_enveloppe
    )

    synchroniser(enveloppe_projet.projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe == dep_detr_enveloppe


@pytest.mark.django_db
@freeze_time("2025-05-06")
def test_refused_dotation_goes_to_the_root_enveloppe_with_a_dsil_and_region_projet(
    perimetres,
):
    arr_dijon, dep_21, region_bfc, *_ = perimetres
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.REFUSE,
    )
    region_dsil_enveloppe = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    dep_dsil_enveloppe_delegated = DsilEnveloppeFactory(
        perimetre=dep_21, annee=2025, parent=region_dsil_enveloppe
    )
    _arr_dsil_enveloppe_delegated = DsilEnveloppeFactory(
        perimetre=arr_dijon, annee=2025, parent=dep_dsil_enveloppe_delegated
    )

    synchroniser(enveloppe_projet.projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe == region_dsil_enveloppe


@pytest.mark.django_db
@freeze_time("2026-05-06")
def test_refused_dotation_creates_the_missing_root_enveloppe(
    perimetres,
):
    arr_dijon, _, region_bfc, *_ = perimetres
    enveloppe_2025 = DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.PROCESSING,
        enveloppe=enveloppe_2025,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.REFUSE,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            2026, 1, 15, tzinfo=UTC
        ),
    )

    synchroniser(enveloppe_projet.projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe.annee == 2026
    assert enveloppe_projet.enveloppe.perimetre == region_bfc
    assert enveloppe_projet.enveloppe.montant == enveloppe_2025.montant


@pytest.mark.django_db
@freeze_time("2026-05-06")
def test_refused_dotation_creates_the_missing_root_enveloppe_without_montant(
    perimetres,
):
    arr_dijon, _, region_bfc, *_ = perimetres
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.PROCESSING,
        enveloppe=DsilEnveloppeFactory(perimetre=region_bfc, annee=2020),
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.REFUSE,
        projet__dossier_ds__ds_date_traitement=timezone.datetime(
            2026, 1, 15, tzinfo=UTC
        ),
    )

    synchroniser(enveloppe_projet.projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe.annee == 2026
    assert enveloppe_projet.enveloppe.montant == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "date_traitement, expected_annee",
    [
        (timezone.datetime(2025, 10, 1, tzinfo=UTC), 2025),
        (timezone.datetime(2025, 11, 1, tzinfo=UTC), 2025),
        (timezone.datetime(2026, 10, 1, tzinfo=UTC), 2026),
        (timezone.datetime(2026, 11, 1, tzinfo=UTC), 2026),
    ],
)
def test_refused_dotation_root_enveloppe_follows_the_treatment_year(
    perimetres, date_traitement, expected_annee
):
    arr_dijon, _, region_bfc, *_ = perimetres
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2025)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2026)
    DsilEnveloppeFactory(perimetre=region_bfc, annee=2027)

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=arr_dijon,
        projet__dossier_ds__ds_state=Dossier.State.REFUSE,
        projet__dossier_ds__ds_date_traitement=date_traitement,
    )

    synchroniser(enveloppe_projet.projet)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe.annee == expected_annee

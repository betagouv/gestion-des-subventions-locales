from datetime import UTC

import pytest
from django.utils import timezone
from freezegun import freeze_time

from gsl.core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.models import Enveloppe
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ....constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ....services.enveloppe_projet_services import EnveloppeProjetService
from ...factories import EnveloppeProjetFactory, ProjetFactory

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
@freeze_time("2026-10-20")
def test_accepted_dotation_leaves_the_campagne_of_its_depot_for_the_treatment_year(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres
    enveloppe_2026 = DetrEnveloppeFactory(perimetre=dep_21, annee=2026)
    DetrEnveloppeFactory(perimetre=dep_21, annee=2027)
    dossier = DossierFactory(
        ds_state=Dossier.State.ACCEPTE,
        annotations_dotation="DETR",
        ds_date_depot=timezone.datetime(2026, 10, 15, tzinfo=UTC),
        ds_date_traitement=timezone.datetime(2026, 10, 20, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    assert dossier.annee_de_campagne == 2027
    enveloppe_ids = set(Enveloppe.objects.values_list("id", flat=True))

    synchroniser(projet)

    enveloppe_projet = projet.enveloppeprojet_set.get()
    assert enveloppe_projet.enveloppe == enveloppe_2026
    assert set(Enveloppe.objects.values_list("id", flat=True)) == enveloppe_ids


@pytest.mark.django_db
@freeze_time("2026-06-20")
def test_accepted_dotation_keeps_the_campagne_of_its_depot_outside_the_autumn(
    perimetres,
):
    arr_dijon, dep_21, *_ = perimetres
    DetrEnveloppeFactory(perimetre=dep_21, annee=2026)
    dossier = DossierFactory(
        ds_state=Dossier.State.ACCEPTE,
        annotations_dotation="DETR",
        ds_date_depot=timezone.datetime(2026, 3, 15, tzinfo=UTC),
        ds_date_traitement=timezone.datetime(2026, 6, 20, tzinfo=UTC),
        perimetre=arr_dijon,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    assert dossier.annee_de_campagne == 2026

    synchroniser(projet)

    enveloppe_projet = projet.enveloppeprojet_set.get()
    assert enveloppe_projet.enveloppe.annee == 2026


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

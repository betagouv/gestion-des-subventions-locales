from datetime import UTC, date, datetime
from datetime import timezone as tz
from decimal import Decimal

import pytest
from django.db import connection

from gsl_core.models import Departement
from gsl_core.tests.factories import (
    ArrondissementFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

from ..models import Projet
from .factories import (
    DemandeurFactory,
    ProcessedProjetFactory,
    ProjetFactory,
    SubmittedProjetFactory,
)

pytestmark = pytest.mark.django_db(transaction=True)


def test_manager():
    ProjetFactory.create_batch(10)
    assert Projet.objects.all().count() == 10


@pytest.mark.django_db
def test_dossier_ds_join(django_assert_num_queries):
    for _ in range(10):
        dossier = DossierFactory()
        ProjetFactory(dossier_ds=dossier)

    with django_assert_num_queries(1):
        projets = Projet.objects.all()
        assert projets.query.select_related == {"dossier_ds": {}}
        for projet in projets:
            _ = projet.dossier_ds.ds_number

    first_sql_query = connection.queries[0]["sql"]
    assert "INNER JOIN" in first_sql_query
    assert "dossier_ds" in first_sql_query


def test_filter_perimetre():
    arrondissement = ArrondissementFactory()
    demandeur_1 = DemandeurFactory(
        arrondissement=arrondissement, departement=arrondissement.departement
    )
    ProjetFactory(demandeur=demandeur_1)

    demandeur_2 = DemandeurFactory()
    ProjetFactory(demandeur=demandeur_2)

    perimetre = PerimetreArrondissementFactory(
        arrondissement=arrondissement,
    )

    assert (
        Projet.objects.for_perimetre(None).count() == 2
    ), "Expect 2 projets for perimetre “None”"
    assert (
        Projet.objects.for_perimetre(perimetre).count() == 1
    ), "Expect 1 projet for perimetre “arrondissement”"
    assert (
        Projet.objects.for_perimetre(perimetre).first().demandeur.arrondissement
        == arrondissement
    )
    assert (
        Projet.objects.for_perimetre(perimetre).first().demandeur.departement
        == arrondissement.departement
    )


@pytest.fixture
def departement() -> Departement:
    return DepartementFactory()


@pytest.fixture
def projets(departement) -> list[Projet]:
    projet_with_departement = ProjetFactory(demandeur__departement=departement)
    projet_without_departement = ProjetFactory()

    return [projet_with_departement, projet_without_departement]


def test_for_staff_user_without_perimetre(projets):
    staff_user = CollegueFactory(is_staff=True, perimetre=None)
    assert Projet.objects.for_user(staff_user).count() == 2


def test_for_super_user_without_perimetre(projets):
    super_user = CollegueFactory(is_superuser=True, perimetre=None)
    assert Projet.objects.for_user(super_user).count() == 2


def test_for_normal_user_without_perimetre(projets):
    user = CollegueFactory(perimetre=None)
    assert Projet.objects.for_user(user).count() == 0


def test_for_staff_user_with_perimetre(departement, projets):
    staff_user_with_perimetre = CollegueFactory(
        is_staff=True, perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    assert Projet.objects.for_user(staff_user_with_perimetre).count() == 1
    assert Projet.objects.for_user(staff_user_with_perimetre).get() == projets[0]


def test_for_super_user_with_perimetre(departement, projets):
    super_user_with_perimetre = CollegueFactory(
        is_superuser=True,
        perimetre=PerimetreDepartementalFactory(departement=departement),
    )
    assert Projet.objects.for_user(super_user_with_perimetre).count() == 1
    assert Projet.objects.for_user(super_user_with_perimetre).get() == projets[0]


def test_for_normal_user_with_perimetre(departement, projets):
    user_with_perimetre = CollegueFactory(
        perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    assert Projet.objects.for_user(user_with_perimetre).count() == 1
    assert Projet.objects.for_user(user_with_perimetre).get() == projets[0]


# Test included_in_enveloppe


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state, ds_date_traitement",
    (
        (Dossier.STATE_EN_CONSTRUCTION, datetime(1999, 1, 1, tzinfo=tz.utc)),
        (Dossier.STATE_EN_INSTRUCTION, datetime(2000, 1, 1, tzinfo=tz.utc)),
        (Dossier.STATE_ACCEPTE, datetime(date.today().year, 1, 1, 0, 0, tzinfo=tz.utc)),
        (
            Dossier.STATE_SANS_SUITE,
            datetime(date.today().year, 1, 1, 0, 0, tzinfo=tz.utc),
        ),
        (Dossier.STATE_REFUSE, datetime(date.today().year, 1, 1, 0, 0, tzinfo=tz.utc)),
    ),
)
def test_for_current_year_with_projet_to_display(state, ds_date_traitement):
    ProjetFactory(
        dossier_ds=DossierFactory(
            ds_state=state,
            ds_date_traitement=ds_date_traitement,
        ),
    )

    qs = Projet.objects.all()
    qs = qs.for_current_year()

    assert qs.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state, ds_date_traitement",
    (
        (
            Dossier.STATE_ACCEPTE,
            datetime(date.today().year - 1, 12, 31, 23, 59, tzinfo=tz.utc),
        ),
        (
            Dossier.STATE_SANS_SUITE,
            datetime(date.today().year - 1, 12, 31, 23, 59, tzinfo=tz.utc),
        ),
        (
            Dossier.STATE_REFUSE,
            datetime(date.today().year - 1, 12, 31, 23, 59, tzinfo=tz.utc),
        ),
    ),
)
def test_for_current_year_with_projet_to_archive(state, ds_date_traitement):
    ProjetFactory(
        dossier_ds=DossierFactory(
            ds_state=state,
            ds_date_traitement=ds_date_traitement,
        ),
    )

    qs = Projet.objects.for_current_year()

    assert qs.count() == 0


def for_year_with_projet_to_display(state, ds_date_traitement):
    ProjetFactory(
        dossier_ds=DossierFactory(
            ds_state=state,
            ds_date_traitement=ds_date_traitement,
        ),
    )

    qs = Projet.objects.all()
    qs = qs.for_year(date.today().year)

    assert qs.count() == 1


# Test for_enveloppe


## Type


@pytest.mark.django_db
@pytest.mark.parametrize(
    "projet_type, enveloppe_type, count",
    [
        ("DSIL", "DSIL", 1),
        ("DSIL", "DETR", 0),
        ("DETR", "DSIL", 0),
        ("DETR", "DETR", 1),
    ],
)
def test_for_enveloppe_with_projet_type_and_enveloppe_type(
    projet_type, enveloppe_type, count
):
    perimetre = PerimetreDepartementalFactory()
    enveloppe_factory = (
        DetrEnveloppeFactory if enveloppe_type == "DETR" else DsilEnveloppeFactory
    )
    enveloppe = enveloppe_factory(annee=2024, perimetre=perimetre)
    ProjetFactory(
        demandeur__departement=perimetre.departement,
        dossier_ds__ds_date_depot=datetime(2024, 3, 1, tzinfo=UTC),
        dossier_ds__ds_date_traitement=datetime(2024, 5, 1, tzinfo=UTC),
        dossier_ds__demande_dispositif_sollicite=projet_type,
    )

    qs = Projet.objects.included_in_enveloppe(enveloppe=enveloppe)

    assert qs.count() == count


## Date


@pytest.mark.django_db
@pytest.mark.parametrize(
    "submitted_year, count",
    [
        (2023, 1),
        (2024, 1),
        (2025, 0),
    ],
)
def test_for_year_2024_and_for_not_processed_states(submitted_year, count):
    perimetre = PerimetreDepartementalFactory()
    enveloppe = DetrEnveloppeFactory(annee=2024, perimetre=perimetre)
    projet = SubmittedProjetFactory(
        dossier_ds__demande_dispositif_sollicite=enveloppe.type,
        dossier_ds__ds_date_depot=datetime(submitted_year, 12, 31, tzinfo=tz.utc),
        dossier_ds__ds_date_traitement=datetime(submitted_year + 1, 5, 1, tzinfo=UTC),
        demandeur__departement=perimetre.departement,
    )
    print(f"Test with {projet.dossier_ds.ds_state}")

    qs = Projet.objects.included_in_enveloppe(enveloppe)

    assert qs.count() == count


@pytest.mark.django_db
@pytest.mark.parametrize(
    "submitted_year, processed_year, count",
    [
        (2023, 2023, 0),
        (2023, 2024, 1),
        (2023, 2025, 1),
        (2024, 2024, 1),
        (2024, 2025, 1),
        (2025, 2025, 0),
    ],
)
def test_for_year_2024_and_for_processed_states(submitted_year, processed_year, count):
    perimetre = PerimetreDepartementalFactory()
    enveloppe = DetrEnveloppeFactory(annee=2024, perimetre=perimetre)
    projet = ProcessedProjetFactory(
        dossier_ds__demande_dispositif_sollicite=enveloppe.type,
        dossier_ds__ds_date_depot=datetime(submitted_year, 12, 31, tzinfo=tz.utc),
        dossier_ds__ds_date_traitement=datetime(processed_year, 12, 31, tzinfo=tz.utc),
        demandeur__departement=perimetre.departement,
    )
    print(f"Test with {projet.dossier_ds.ds_state}")

    qs = Projet.objects.included_in_enveloppe(enveloppe)

    assert qs.count() == count


# Test processed_in_enveloppe

## Date


@pytest.mark.django_db
@pytest.mark.parametrize(
    "processed_year, count",
    [
        (2023, 0),
        (2024, 1),
        (2025, 0),
    ],
)
@pytest.mark.django_db
def test_processed_in_enveloppe_with_different_processed_dates(processed_year, count):
    perimetre = PerimetreDepartementalFactory()
    enveloppe = DetrEnveloppeFactory(annee=2024, perimetre=perimetre)
    projet = ProcessedProjetFactory(
        dossier_ds__demande_dispositif_sollicite=enveloppe.type,
        dossier_ds__ds_date_traitement=datetime(processed_year, 1, 1, tzinfo=tz.utc),
        demandeur__departement=perimetre.departement,
    )
    print(f"Test with {projet.dossier_ds.ds_state}")

    qs = Projet.objects.processed_in_enveloppe(enveloppe)

    assert qs.count() == count


@pytest.mark.django_db
def test_accept_projet():
    projet = ProjetFactory(assiette=10_000)
    assert projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROVISOIRE, montant=1_000
    )
    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_REFUSED, montant=2_000
    )
    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROCESSING, montant=3_000
    )
    assert SimulationProjet.objects.filter(projet=projet).count() == 3

    enveloppe = DetrEnveloppeFactory(annee=2025)

    projet.accept(montant=5_000, enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        projet=projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 50

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet_update_programmation_projet():
    projet = ProjetFactory(assiette=9_000, status=Projet.STATUS_REFUSED)

    enveloppe = DetrEnveloppeFactory(annee=2025)
    ProgrammationProjetFactory(
        projet=projet,
        enveloppe=enveloppe,
        montant=0,
        status=ProgrammationProjet.STATUS_REFUSED,
    )

    projet.accept(montant=5_000, enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()
    assert projet.status == Projet.STATUS_ACCEPTED

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == Decimal("55.56")
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED

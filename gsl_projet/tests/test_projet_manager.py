from datetime import UTC, date, datetime
from datetime import timezone as tz

import pytest
from django.db import connection

from gsl_core.models import Departement, Perimetre
from gsl_core.tests.factories import (
    ArrondissementFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory

from ..models import Projet
from .factories import (
    DotationProjetFactory,
    ProcessedProjetFactory,
    ProjetFactory,
    SubmittedProjetFactory,
)

pytestmark = pytest.mark.django_db(transaction=True)


# General tests ========================================================================


def test_manager():
    ProjetFactory.create_batch(10)
    assert Projet.objects.all().count() == 10


@pytest.mark.django_db
def test_dossier_ds_join(django_assert_num_queries):
    for _ in range(10):
        dossier = DossierFactory()
        ProjetFactory(dossier_ds=dossier)

    with django_assert_num_queries(2):
        projets = Projet.objects.all()
        assert "dossier_ds" in projets.query.select_related
        for projet in projets:
            _ = projet.dossier_ds.ds_number
            _ = projet.dotationprojet_set.count()

    first_sql_query = connection.queries[0]["sql"]
    assert "INNER JOIN" in first_sql_query
    assert "dossier_ds" in first_sql_query

    second_sql_query = connection.queries[1]["sql"]
    assert "dotationprojet" in second_sql_query


# Filter on perimetre ==================================================================


def test_filter_perimetre_arrondissement():
    # Arrange
    arrondissement = ArrondissementFactory()
    perimetre = PerimetreArrondissementFactory(arrondissement=arrondissement)
    arrondissement_projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    unrelated_projet = ProjetFactory(
        dossier_ds__perimetre=PerimetreArrondissementFactory()
    )

    # Act
    unfiltered_projets = set(Projet.objects.for_perimetre(None).all())
    arrondissement_projets = set(Projet.objects.for_perimetre(perimetre).all())

    # Assert
    assert len(unfiltered_projets) == 2
    assert len(arrondissement_projets) == 1
    assert arrondissement_projet in arrondissement_projets
    assert unrelated_projet not in arrondissement_projets


# Filter on user =======================================================================


@pytest.fixture
def departement() -> Departement:
    return DepartementFactory()


@pytest.fixture
def projets(departement) -> list[Projet]:
    arrondissement = ArrondissementFactory(departement=departement)
    projet_with_arrondissement = ProjetFactory(
        dossier_ds__perimetre=PerimetreArrondissementFactory(
            departement=departement, arrondissement=arrondissement
        )
    )
    projet_with_departement = ProjetFactory(
        dossier_ds__perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    projet_without_perimetre = ProjetFactory()

    return [
        projet_with_arrondissement,
        projet_with_departement,
        projet_without_perimetre,
    ]


def test_for_staff_user_without_perimetre(projets):
    staff_user = CollegueFactory(is_staff=True, perimetre=None)
    assert Projet.objects.for_user(staff_user).count() == len(projets)


def test_for_super_user_without_perimetre(projets):
    super_user = CollegueFactory(is_superuser=True, perimetre=None)
    assert Projet.objects.for_user(super_user).count() == len(projets)


def test_for_normal_user_without_perimetre(projets):
    user = CollegueFactory(perimetre=None)
    assert Projet.objects.for_user(user).count() == 0


def test_for_staff_user_with_perimetre(departement, projets):
    perimetre = Perimetre.objects.get(arrondissement=None, departement=departement)
    staff_user_with_perimetre = CollegueFactory(is_staff=True, perimetre=perimetre)

    staff_user_projects = list(Projet.objects.for_user(staff_user_with_perimetre).all())

    assert len(staff_user_projects) == 2, (
        "We should only get projects within user’s perimeter, even staff"
    )
    assert projets[0] in staff_user_projects
    assert projets[1] in staff_user_projects


def test_for_super_user_with_perimetre(departement, projets):
    perimetre = Perimetre.objects.get(arrondissement=None, departement=departement)
    superuser_user_with_perimetre = CollegueFactory(
        is_superuser=True, perimetre=perimetre
    )

    superuser_projects = list(
        Projet.objects.for_user(superuser_user_with_perimetre).all()
    )

    assert len(superuser_projects) == 2, (
        "We should only get projects within user’s perimeter, even superuser"
    )
    assert projets[0] in superuser_projects
    assert projets[1] in superuser_projects


def test_for_normal_user_with_perimetre(departement, projets):
    perimetre = Perimetre.objects.get(arrondissement=None, departement=departement)
    user_with_perimetre = CollegueFactory(is_staff=True, perimetre=perimetre)

    user_projects = list(Projet.objects.for_user(user_with_perimetre).all())

    assert len(user_projects) == 2, (
        "We should only get projects within user’s perimeter"
    )
    assert projets[0] in user_projects
    assert projets[1] in user_projects


# Filter included_in_enveloppe =========================================================


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


# Filter for_enveloppe =================================================================

# Type ---------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "projet_dotation, enveloppe_dotation, count",
    [
        ("DSIL", "DSIL", 1),
        ("DSIL", "DETR", 0),
        ("DETR", "DSIL", 0),
        ("DETR", "DETR", 1),
    ],
)
def test_for_enveloppe_with_projet_type_and_enveloppe_dotation(
    projet_dotation, enveloppe_dotation, count
):
    perimetre = PerimetreDepartementalFactory()
    enveloppe_factory = (
        DetrEnveloppeFactory if enveloppe_dotation == "DETR" else DsilEnveloppeFactory
    )
    enveloppe = enveloppe_factory(annee=2024, perimetre=perimetre)
    projet = ProjetFactory(
        dossier_ds__perimetre=perimetre,
        dossier_ds__ds_date_depot=datetime(2024, 3, 1, tzinfo=UTC),
        dossier_ds__ds_date_traitement=datetime(2024, 5, 1, tzinfo=UTC),
    )
    DotationProjetFactory(projet=projet, dotation=projet_dotation)

    qs = Projet.objects.included_in_enveloppe(enveloppe=enveloppe)

    assert qs.count() == count


# Date ---------------------------------------------------------------------------------


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
        dossier_ds__demande_dispositif_sollicite=enveloppe.dotation,
        dossier_ds__ds_date_depot=datetime(submitted_year, 12, 31, tzinfo=tz.utc),
        dossier_ds__ds_date_traitement=datetime(submitted_year + 1, 5, 1, tzinfo=UTC),
        dossier_ds__perimetre=perimetre,
    )
    DotationProjetFactory(projet=projet, dotation=enveloppe.dotation)
    print(f"Test with {projet.dossier_ds.ds_state}")

    qs = Projet.objects.included_in_enveloppe(enveloppe)

    assert qs.count() == count


# Filter included_in_enveloppe ========================================================

# Date ---------------------------------------------------------------------------------


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
    enveloppe = DsilEnveloppeFactory(annee=2024, perimetre=perimetre)
    projet = ProcessedProjetFactory(
        dossier_ds__ds_date_depot=datetime(submitted_year, 12, 31, tzinfo=tz.utc),
        dossier_ds__ds_date_traitement=datetime(processed_year, 12, 31, tzinfo=tz.utc),
        dossier_ds__perimetre=perimetre,
    )
    DotationProjetFactory(projet=projet, dotation=enveloppe.dotation)
    print(f"Test with {projet.dossier_ds.ds_state}")

    qs = Projet.objects.included_in_enveloppe(enveloppe)

    assert qs.count() == count

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gsl.core.models import Departement, Perimetre
from gsl.core.tests.factories import (
    ArrondissementFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl.notification.tests.factories import LettreEtArreteSignesFactory
from gsl.programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..constants import DOTATION_DETR, DOTATION_DSIL, ProjetStatus
from ..models import Projet
from .factories import (
    EnveloppeProjetFactory,
    ProjetFactory,
)

pytestmark = pytest.mark.django_db


# General tests ========================================================================


def test_manager():
    ProjetFactory.create_batch(10)
    assert Projet.objects.all().count() == 10


def test_manager_excludes_projets_with_inactive_dossier():
    ProjetFactory.create_batch(3)
    ProjetFactory(dossier_ds__is_active=False)

    assert Projet.objects.active().count() == 3


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
            _ = projet.enveloppeprojet_set.count()

    first_sql_query = connection.queries[0]["sql"]
    assert "INNER JOIN" in first_sql_query
    assert "dossier_ds" in first_sql_query

    second_sql_query = connection.queries[1]["sql"]
    assert "enveloppeprojet" in second_sql_query


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


# Filter for_campagne =========================================================


def test_for_campagne_returns_a_projet_of_that_campagne():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DetrEnveloppeFactory(annee=2025, perimetre=perimetre),
    )

    assert list(Projet.objects.for_campagne(2025)) == [projet]


def test_for_campagne_ignores_a_projet_of_another_campagne():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DetrEnveloppeFactory(annee=2026, perimetre=perimetre),
    )

    assert Projet.objects.for_campagne(2025).count() == 0


def test_for_campagne_ignores_an_historised_enveloppe_projet():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DetrEnveloppeFactory(annee=2025, perimetre=perimetre),
        is_courant=False,
    )

    assert Projet.objects.for_campagne(2025).count() == 0


def test_for_campagne_returns_a_double_dotation_projet_once():
    perimetre = PerimetreDepartementalFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DetrEnveloppeFactory(annee=2025, perimetre=perimetre),
    )
    EnveloppeProjetFactory(
        projet=projet,
        enveloppe=DsilEnveloppeFactory(annee=2025, perimetre=perimetre),
    )

    assert list(Projet.objects.for_campagne(2025)) == [projet]


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


# Filter with_missing_annotations ======================================================


@pytest.mark.django_db
def test_with_missing_annotations():
    """Projets with accepted dossier but incomplete DETR/DSIL annotations."""
    # Should NOT be included (non-accepted state)
    ProjetFactory(
        dossier_ds=DossierFactory(ds_state=Dossier.State.EN_INSTRUCTION),
    )
    # Should be included (accepted, no annotations_dotation)
    with_missing = ProjetFactory(
        dossier_ds=DossierFactory(
            ds_state=Dossier.State.ACCEPTE,
            annotations_dotation="",
        ),
    )
    # Should be included (accepted, DETR but missing assiette)
    with_missing_detr = ProjetFactory(
        dossier_ds=DossierFactory(
            ds_state=Dossier.State.ACCEPTE,
            annotations_dotation="DETR",
            annotations_assiette_detr=None,
            annotations_montant_accorde_detr=50,
        ),
    )
    # Should NOT be included (accepted, DETR complete)
    ProjetFactory(
        dossier_ds=DossierFactory(
            ds_state=Dossier.State.ACCEPTE,
            annotations_dotation="DETR",
            annotations_assiette_detr=100,
            annotations_montant_accorde_detr=50,
        ),
    )

    qs = Projet.objects.with_missing_annotations()
    ids = set(qs.values_list("pk", flat=True))

    assert len(ids) == 2
    assert with_missing.pk in ids
    assert with_missing_detr.pk in ids


# Annotate status =====================================================================


def test_annotate_status_query_count():
    for status in (
        ProjetStatus.PROCESSING,
        ProjetStatus.ACCEPTED,
        ProjetStatus.REFUSED,
    ):
        projet = ProjetFactory()
        _create_enveloppe_projet(projet, DOTATION_DETR, status)

    with CaptureQueriesContext(connection) as ctx:
        statuses = {projet.status for projet in Projet.objects.annotate_status()}

    assert statuses == {
        ProjetStatus.PROCESSING,
        ProjetStatus.ACCEPTED,
        ProjetStatus.REFUSED,
    }
    # 1 query for the projets + 1 prefetch of enveloppeprojet_set (ProjetManager);
    # projet.status reads the annotation, without any extra query
    assert len(ctx.captured_queries) == 2
    # 1 EXISTS per status: processing, accepted, dismissed, refused
    assert ctx.captured_queries[0]["sql"].upper().count("EXISTS") == 4


# Filter has_document_ready ============================================================

ACCEPTED_WITH_DOC = "accepted_with_doc"
ACCEPTED_WITHOUT_DOC = "accepted_without_doc"


def test_has_document_ready_excludes_processing_projet():
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.PROCESSING)

    assert projet not in Projet.objects.has_document_ready()


def test_has_document_ready_excludes_accepted_projet_without_signed_document():
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ACCEPTED_WITHOUT_DOC)

    assert projet not in Projet.objects.has_document_ready()


@pytest.mark.parametrize(
    "other_status",
    (
        ProjetStatus.PROCESSING,
        ProjetStatus.REFUSED,
        ProjetStatus.DISMISSED,
        ACCEPTED_WITH_DOC,
        ACCEPTED_WITHOUT_DOC,
    ),
)
def test_has_document_ready_excludes_double_dotation_projet_with_a_processing_dotation(
    other_status,
):
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.PROCESSING)
    _create_enveloppe_projet(projet, DOTATION_DSIL, other_status)

    assert projet not in Projet.objects.has_document_ready()


@pytest.mark.parametrize(
    "other_status",
    (
        ProjetStatus.REFUSED,
        ProjetStatus.DISMISSED,
        ACCEPTED_WITH_DOC,
        ACCEPTED_WITHOUT_DOC,
    ),
)
def test_has_document_ready_excludes_double_dotation_projet_with_an_accepted_dotation_without_signed_document(
    other_status,
):
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ACCEPTED_WITHOUT_DOC)
    _create_enveloppe_projet(projet, DOTATION_DSIL, other_status)

    assert projet not in Projet.objects.has_document_ready()


@pytest.mark.parametrize(
    "status", (ProjetStatus.REFUSED, ProjetStatus.DISMISSED, ACCEPTED_WITH_DOC)
)
def test_has_document_ready_includes_single_dotation_projet(status):
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, status)

    assert projet in Projet.objects.has_document_ready()


@pytest.mark.parametrize(
    "detr_status", (ProjetStatus.REFUSED, ProjetStatus.DISMISSED, ACCEPTED_WITH_DOC)
)
@pytest.mark.parametrize(
    "dsil_status", (ProjetStatus.REFUSED, ProjetStatus.DISMISSED, ACCEPTED_WITH_DOC)
)
def test_has_document_ready_includes_double_dotation_projet(detr_status, dsil_status):
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, detr_status)
    _create_enveloppe_projet(projet, DOTATION_DSIL, dsil_status)

    assert projet in Projet.objects.has_document_ready()


# Filter accepted ======================================================================


def test_accepted_includes_single_dotation_accepted_projet():
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.ACCEPTED)

    assert projet in Projet.objects.accepted()


@pytest.mark.parametrize(
    "status",
    (ProjetStatus.PROCESSING, ProjetStatus.REFUSED, ProjetStatus.DISMISSED),
)
def test_accepted_excludes_single_dotation_not_accepted_projet(status):
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, status)

    assert projet not in Projet.objects.accepted()


def test_accepted_excludes_projet_without_enveloppe_projet():
    projet = ProjetFactory()

    assert projet not in Projet.objects.accepted()


@pytest.mark.parametrize(
    "other_status",
    (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED, ProjetStatus.DISMISSED),
)
def test_accepted_includes_double_dotation_projet_with_an_accepted_dotation(
    other_status,
):
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.ACCEPTED)
    _create_enveloppe_projet(projet, DOTATION_DSIL, other_status)

    assert projet in Projet.objects.accepted()


def test_accepted_excludes_double_dotation_projet_with_a_processing_dotation():
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.ACCEPTED)
    _create_enveloppe_projet(projet, DOTATION_DSIL, ProjetStatus.PROCESSING)

    assert projet not in Projet.objects.accepted()


def test_accepted_excludes_double_dotation_projet_refused_and_dismissed():
    projet = ProjetFactory()
    _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.REFUSED)
    _create_enveloppe_projet(projet, DOTATION_DSIL, ProjetStatus.DISMISSED)

    assert projet not in Projet.objects.accepted()


def test_accepted_query_count():
    for _ in range(3):
        projet = ProjetFactory()
        _create_enveloppe_projet(projet, DOTATION_DETR, ProjetStatus.ACCEPTED)
        _create_enveloppe_projet(projet, DOTATION_DSIL, ProjetStatus.REFUSED)

    with CaptureQueriesContext(connection) as ctx:
        projets = list(Projet.objects.accepted())

    assert len(projets) == 3
    # 1 query for the projets + 1 prefetch of enveloppeprojet_set (ProjetManager)
    assert len(ctx.captured_queries) == 2
    # 1 EXISTS for an accepted dotation + 1 NOT EXISTS for a processing one
    assert ctx.captured_queries[0]["sql"].upper().count("EXISTS") == 2


def _create_enveloppe_projet(projet, dotation, status):
    if status == ACCEPTED_WITH_DOC:
        enveloppe_projet = EnveloppeProjetFactory(
            projet=projet, dotation=dotation, status=ProjetStatus.ACCEPTED
        )
        LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)
        return enveloppe_projet
    if status == ACCEPTED_WITHOUT_DOC:
        status = ProjetStatus.ACCEPTED
    return EnveloppeProjetFactory(projet=projet, dotation=dotation, status=status)

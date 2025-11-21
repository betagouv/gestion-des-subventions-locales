from datetime import UTC, datetime
from unittest import mock

import pytest

from gsl_core.tests.factories import (
    CommuneFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.tasks import (
    task_create_or_update_projet_and_co_from_dossier,
    task_create_or_update_projets_and_co_batch,
    task_create_or_update_projets_and_co_from_all_dossiers,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

# Fixtures


@pytest.fixture
def commune():
    return CommuneFactory()


@pytest.fixture
def perimetre_arrondissement(commune):
    return PerimetreArrondissementFactory(arrondissement=commune.arrondissement)


@pytest.fixture
def perimetre_departement(perimetre_arrondissement):
    return PerimetreDepartementalFactory(
        departement=perimetre_arrondissement.departement
    )


@pytest.fixture
def detr_enveloppe(perimetre_departement):
    return DetrEnveloppeFactory(perimetre=perimetre_departement, annee=2024)


# Tests


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_an_other_dotation_than_existing_one(
    commune,
):
    """
    On teste le fait qu'un dossier DS avec une annotation_dotation donnée ne supprime pas les dotation_projets avec une autre dotation dans notre application.
    Désormais, on ignore l'annotation dotation lorsque le dossier n'est pas accepté. Donc ici, la dotation DSIL ne sera pas instanciée pour ce projet.
    """
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_CONSTRUCTION,
        annotations_dotation=DOTATION_DSIL,
        demande_montant=400,
        finance_cout_total=4_000,
        ds_demandeur__address__commune=commune,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    detr_dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )

    # --

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    # --

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1

    detr_dotation_projet.refresh_from_db()  # always exists
    assert detr_dotation_projet.status == PROJET_STATUS_ACCEPTED


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_with_construction_one(
    commune,
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_CONSTRUCTION,
        annotations_dotation=DOTATION_DETR,
        demande_montant=400,
        finance_cout_total=4_000,
        ds_demandeur__address__commune=commune,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=400,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=400,
        notified_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
    )
    # Notified or not, projet should stay accepted

    assert projet.status == PROJET_STATUS_ACCEPTED

    # --

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    # --

    projet.refresh_from_db()
    assert projet.status == PROJET_STATUS_ACCEPTED

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1
    dotation_projet = dotation_projets.first()  # always exists
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette is None
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED  # always exists

    for simulation_projet in dotation_projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 400
        assert simulation_projet.taux == 10

    programmation_projet = dotation_projet.programmation_projet  # always exists
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.montant == 400
    assert programmation_projet.taux == 10


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_with_instruction_one_and_with_an_accepted_but_not_notified_projet(
    commune,
):
    """
    On teste le fait qu'un dossier DS en instruction avec un dotation_projet accepté mais pas encore notifié
    ne modifie pas le statut du projet ni des dotation_projets, simulation_projets et programmation_projets associés.
    """
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        annotations_dotation=DOTATION_DETR,
        demande_montant=400,
        finance_cout_total=4_000,
        ds_demandeur__address__commune=commune,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=400,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=400,
        notified_at=None,
    )

    assert projet.status == PROJET_STATUS_ACCEPTED

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    projet.refresh_from_db()
    assert projet.status == PROJET_STATUS_ACCEPTED

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1
    dotation_projet = dotation_projets.first()
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette is None
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED

    for simulation_projet in dotation_projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 400
        assert simulation_projet.taux == 10

    programmation_projet = dotation_projet.programmation_projet
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.notified_at is None


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_with_instruction_one_and_with_an_accepted_and_notified_projet(
    commune,
):
    """
    On teste le fait qu'un dossier DS en instruction avec un dotation_projet accepté mais pas encore notifié
    ne modifie pas le statut du projet ni des dotation_projets, simulation_projets et programmation_projets associés.
    """
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_INSTRUCTION,
        annotations_dotation=DOTATION_DETR,
        demande_montant=400,
        finance_cout_total=4_000,
        ds_demandeur__address__commune=commune,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=400,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=400,
        notified_at=None,
    )

    assert projet.status == PROJET_STATUS_ACCEPTED

    # --

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    # --

    projet.refresh_from_db()
    assert projet.status == PROJET_STATUS_ACCEPTED

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1
    dotation_projet = dotation_projets.first()
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette is None
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED

    for simulation_projet in dotation_projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 400
        assert simulation_projet.taux == 10

    programmation_projet = dotation_projet.programmation_projet
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.montant == 400
    assert programmation_projet.taux == 10


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_with_accepted(
    commune, detr_enveloppe
):
    """
    On teste le fait qu'un dossier DS accepté avec un dotation_projet refusé bascule le projet et tout le reste en accepté
    """
    dossier = DossierFactory(
        ds_state=Dossier.STATE_ACCEPTE,
        ds_demandeur__address__commune=commune,
        ds_date_traitement=datetime(2024, 1, 15, tzinfo=UTC),
        annotations_dotation=DOTATION_DETR,
        annotations_montant_accorde_detr=5_000,
        annotations_assiette_detr=50_000,
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_REFUSED,
        montant=0,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_REFUSED,
        enveloppe=detr_enveloppe,
    )
    assert projet.status == PROJET_STATUS_REFUSED

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    projet.refresh_from_db()
    assert projet.status == PROJET_STATUS_ACCEPTED

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1
    dotation_projet = dotation_projets.first()
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette == 50_000
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED

    for simulation_projet in dotation_projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 10

    programmation_projet = dotation_projet.programmation_projet
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 10


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_with_refused(
    commune, detr_enveloppe
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_REFUSE,
        annotations_dotation=DOTATION_DETR,
        ds_demandeur__address__commune=commune,
        ds_date_traitement=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
    )
    projet = ProjetFactory(dossier_ds=dossier, perimetre=detr_enveloppe.perimetre)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=500,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=detr_enveloppe,
        montant=500,
    )
    assert projet.status == PROJET_STATUS_ACCEPTED

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    projet.refresh_from_db()
    assert projet.status == PROJET_STATUS_REFUSED

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1
    dotation_projet = dotation_projets.first()
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette is None
    assert dotation_projet.status == PROJET_STATUS_REFUSED

    for simulation_projet in dotation_projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0

    programmation_projet = dotation_projet.programmation_projet
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.notified_at == datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_with_dismissed(
    commune, detr_enveloppe
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_SANS_SUITE,
        annotations_dotation=DOTATION_DETR,
        ds_demandeur__address__commune=commune,
        ds_date_traitement=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
    )
    projet = ProjetFactory(dossier_ds=dossier)
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=500,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=detr_enveloppe,
        montant=500,
    )
    assert projet.status == PROJET_STATUS_ACCEPTED

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    projet.refresh_from_db()
    assert projet.status == PROJET_STATUS_DISMISSED

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    assert dotation_projets.count() == 1
    dotation_projet = dotation_projets.first()
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette is None
    assert dotation_projet.status == PROJET_STATUS_DISMISSED

    for simulation_projet in dotation_projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0

    programmation_projet = dotation_projet.programmation_projet
    assert programmation_projet.status == ProgrammationProjet.STATUS_DISMISSED
    assert programmation_projet.notified_at == datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_task_create_or_update_projet_and_co_from_dossier_update_from_annotations(
    commune, detr_enveloppe
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_ACCEPTE,
        annotations_dotation=DOTATION_DETR,
        annotations_assiette_detr=60_000,
        annotations_montant_accorde_detr=6_000,
        annotations_is_budget_vert=True,
        annotations_is_qpv=True,
        annotations_is_crte=True,
        ds_demandeur__address__commune=commune,
        ds_date_traitement=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
    )
    projet = ProjetFactory(
        dossier_ds=dossier,
        is_budget_vert=False,
        is_in_qpv=False,
        is_attached_to_a_crte=False,
    )
    dotation_projet = DotationProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        assiette=50_000,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=detr_enveloppe,
        montant=500,
    )

    task_create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    projet.refresh_from_db()
    assert projet.is_budget_vert is True
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True

    dotation_projets = DotationProjet.objects.filter(projet=projet)
    dotation_projet = dotation_projets.first()
    assert dotation_projet.dotation == DOTATION_DETR
    assert dotation_projet.assiette == 60_000
    assert dotation_projet.programmation_projet.montant == 6_000


@pytest.mark.django_db
def test_create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers():
    for i in range(10):
        DossierFactory(ds_number=i, ds_state="state")

    with mock.patch(
        "gsl_projet.tasks.task_create_or_update_projets_and_co_batch.delay"
    ) as mock_create_or_update_projets_batch:
        task_create_or_update_projets_and_co_from_all_dossiers(batch_size=5)

        assert mock_create_or_update_projets_batch.call_count == 2

        mock_create_or_update_projets_batch.assert_any_call((0, 1, 2, 3, 4))
        mock_create_or_update_projets_batch.assert_any_call((5, 6, 7, 8, 9))


@pytest.mark.django_db
def test_create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers_with_no_dossiers():
    with mock.patch(
        "gsl_projet.tasks.task_create_or_update_projets_and_co_batch.delay"
    ) as mock_delay:
        task_create_or_update_projets_and_co_from_all_dossiers(batch_size=5)

        mock_delay.assert_not_called()


@pytest.mark.django_db
def test_create_or_update_projets_batch():
    with mock.patch(
        "gsl_projet.tasks.task_create_or_update_projet_and_co_from_dossier.delay"
    ) as mock_delay:
        task_create_or_update_projets_and_co_batch((1, 2, 3))
        assert mock_delay.call_count == 3

        mock_delay.assert_any_call(1)
        mock_delay.assert_any_call(2)
        mock_delay.assert_any_call(3)

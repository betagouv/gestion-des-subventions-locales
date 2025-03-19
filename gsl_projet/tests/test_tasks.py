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
from gsl_projet.models import Projet
from gsl_projet.tasks import (
    create_all_projets_from_dossiers,
    create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier,
    create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers,
    create_or_update_projets_batch,
)
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory


@pytest.mark.django_db
def test_create_all_projets():
    dossier_en_construction = DossierFactory(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    DossierFactory(ds_state="")
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        create_all_projets_from_dossiers()
        task_mock.assert_called_once_with(dossier_en_construction.ds_number)


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
    return DetrEnveloppeFactory(perimetre=perimetre_departement)


@pytest.mark.django_db
def test_create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier_with_construction_one(
    commune, perimetre_departement
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_CONSTRUCTION,
        annotations_dotation=Dossier.DOTATION_DETR,
        demande_montant=400,
        finance_cout_total=4_000,
        ds_demandeur__address__commune=commune,
    )
    projet = ProjetFactory(dossier_ds=dossier, status=Projet.STATUS_ACCEPTED)
    SimulationProjetFactory.create_batch(
        2, projet=projet, status=SimulationProjet.STATUS_ACCEPTED, montant=500, taux=0.5
    )
    ProgrammationProjetFactory(
        projet=projet, status=ProgrammationProjet.STATUS_ACCEPTED
    )

    create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier(
        dossier.ds_number
    )

    projet.refresh_from_db()
    assert projet.status == Projet.STATUS_PROCESSING
    for simulation_projet in projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 400
        assert simulation_projet.taux == 10

    assert ProgrammationProjet.objects.filter(projet=projet).count() == 0


@pytest.mark.django_db
def test_create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier_with_accepted(
    commune, detr_enveloppe
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_ACCEPTE,
        ds_demandeur__address__commune=commune,
        annotations_dotation=Dossier.DOTATION_DETR,
        annotations_montant_accorde=5_000,
        annotations_taux=10,
        annotations_assiette=50_000,
    )
    projet = ProjetFactory(dossier_ds=dossier, status=Projet.STATUS_REFUSED)
    SimulationProjetFactory.create_batch(
        2, projet=projet, status=SimulationProjet.STATUS_REFUSED, montant=0, taux=0
    )
    ProgrammationProjetFactory(
        projet=projet,
        status=ProgrammationProjet.STATUS_REFUSED,
        enveloppe=detr_enveloppe,
    )
    create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier(
        dossier.ds_number
    )

    projet.refresh_from_db()
    assert projet.status == Projet.STATUS_ACCEPTED
    for simulation_projet in projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 10

    programmation_projet = ProgrammationProjet.objects.get(projet=projet)
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 10


@pytest.mark.django_db
def test_create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier_with_refused(
    commune, detr_enveloppe
):
    dossier = DossierFactory(
        ds_state=Dossier.STATE_REFUSE,
        annotations_dotation=Dossier.DOTATION_DETR,
        ds_demandeur__address__commune=commune,
    )
    projet = ProjetFactory(dossier_ds=dossier, status=Projet.STATUS_ACCEPTED)
    SimulationProjetFactory.create_batch(
        2, projet=projet, status=SimulationProjet.STATUS_ACCEPTED, montant=500, taux=10
    )
    ProgrammationProjetFactory(
        projet=projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=detr_enveloppe,
        montant=500,
        taux=10,
    )
    create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier(
        dossier.ds_number
    )

    projet.refresh_from_db()
    assert projet.status == Projet.STATUS_REFUSED
    for simulation_projet in projet.simulationprojet_set.all():
        assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0

    programmation_projet = ProgrammationProjet.objects.get(projet=projet)
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0


@pytest.mark.django_db
def test_create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers():
    for i in range(10):
        DossierFactory(ds_number=i, ds_state="state")

    with mock.patch(
        "gsl_projet.tasks.create_or_update_projets_batch.delay"
    ) as mock_create_or_update_projets_batch:
        create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers(
            batch_size=5
        )

        assert mock_create_or_update_projets_batch.call_count == 2

        mock_create_or_update_projets_batch.assert_any_call((0, 1, 2, 3, 4))
        mock_create_or_update_projets_batch.assert_any_call((5, 6, 7, 8, 9))


@pytest.mark.django_db
def test_create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers_with_no_dossiers():
    with mock.patch(
        "gsl_projet.tasks.create_or_update_projets_batch.delay"
    ) as mock_delay:
        create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers(
            batch_size=5
        )

        mock_delay.assert_not_called()


@pytest.mark.django_db
def test_create_or_update_projets_batch():
    with mock.patch(
        "gsl_projet.tasks.create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier.delay"
    ) as mock_delay:
        create_or_update_projets_batch((1, 2, 3))
        assert mock_delay.call_count == 3

        mock_delay.assert_any_call(1)
        mock_delay.assert_any_call(2)
        mock_delay.assert_any_call(3)

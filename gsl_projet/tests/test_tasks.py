from unittest import mock

import pytest

from gsl_core.tests.factories import PerimetreDepartementalFactory
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
)
from gsl_projet.tests.factories import DemandeurFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory


@pytest.mark.django_db
def test_create_all_projets():
    dossier_en_construction = DossierFactory(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    DossierFactory(ds_state="")
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        create_all_projets_from_dossiers()
        task_mock.assert_called_once_with(dossier_en_construction.ds_number)


@pytest.mark.django_db
def test_create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier_with_construction_one():
    dossier = DossierFactory(
        ds_state=Dossier.STATE_EN_CONSTRUCTION,
        annotations_dotation=Dossier.DOTATION_DETR,
        demande_montant=400,
        finance_cout_total=4_000,
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
def test_create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier_with_accepted():
    perimetre = PerimetreDepartementalFactory(arrondissement=None)
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
    demandeur = DemandeurFactory(departement=perimetre.departement)
    dossier = DossierFactory(
        ds_state=Dossier.STATE_ACCEPTE,
        annotations_dotation=Dossier.DOTATION_DETR,
        annotations_montant_accorde=5_000,
        annotations_taux=10,
        annotations_assiette=50_000,
        ds_demandeur__address__commune__departement=demandeur.departement,
    )
    projet = ProjetFactory(
        dossier_ds=dossier, status=Projet.STATUS_REFUSED, demandeur=demandeur
    )
    SimulationProjetFactory.create_batch(
        2, projet=projet, status=SimulationProjet.STATUS_REFUSED, montant=0, taux=0
    )
    ProgrammationProjetFactory(
        projet=projet, status=ProgrammationProjet.STATUS_REFUSED, enveloppe=enveloppe
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
def test_create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier_with_refused():
    perimetre = PerimetreDepartementalFactory(arrondissement=None)
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
    demandeur = DemandeurFactory(departement=perimetre.departement)
    dossier = DossierFactory(
        ds_state=Dossier.STATE_REFUSE,
        annotations_dotation=Dossier.DOTATION_DETR,
        ds_demandeur__address__commune__departement=demandeur.departement,
    )
    projet = ProjetFactory(
        dossier_ds=dossier, status=Projet.STATUS_ACCEPTED, demandeur=demandeur
    )
    SimulationProjetFactory.create_batch(
        2, projet=projet, status=SimulationProjet.STATUS_ACCEPTED, montant=500, taux=10
    )
    ProgrammationProjetFactory(
        projet=projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        enveloppe=enveloppe,
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

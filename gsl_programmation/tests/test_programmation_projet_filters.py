from decimal import Decimal

import pytest
from django.test import RequestFactory

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.tests.factories import (
    CategorieDetrFactory,
    DemandeurFactory,
    DotationProjetFactory,
    ProjetFactory,
)


@pytest.fixture
def arrondissement():
    return PerimetreArrondissementFactory()


@pytest.fixture
def departement(arrondissement):
    return PerimetreDepartementalFactory(
        departement=arrondissement.departement, region=arrondissement.region
    )


@pytest.fixture
def region(arrondissement):
    return PerimetreRegionalFactory(region=arrondissement.region)


@pytest.fixture
def enveloppe(departement):
    return DetrEnveloppeFactory(
        dotation=DOTATION_DETR,
        perimetre=departement,
        annee=2024,
        montant=Decimal("1000000.00"),
    )


@pytest.fixture
def user(departement):
    return CollegueFactory(perimetre=departement)


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory, user):
    request = request_factory.get("/")
    request.user = user
    request.resolver_match = type(
        "MockResolverMatch", (), {"kwargs": {"dotation": DOTATION_DETR}}
    )()
    return request


pytestmark = pytest.mark.django_db


class TestProgrammationProjetFilters:
    def test_porteur_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre par type de porteur de projet"""
        # Créer différents types de porteurs
        nature_commune = NaturePorteurProjetFactory(type=NaturePorteurProjet.COMMUNES)
        nature_departement = NaturePorteurProjetFactory(type=NaturePorteurProjet.EPCI)

        # Créer des dossiers avec différents porteurs
        dossier_commune = DossierFactory(porteur_de_projet_nature=nature_commune)
        dossier_departement = DossierFactory(
            porteur_de_projet_nature=nature_departement
        )

        # Créer des projets et programmations
        projet_commune = ProjetFactory(
            dossier_ds=dossier_commune, perimetre=arrondissement
        )
        projet_departement = ProjetFactory(
            dossier_ds=dossier_departement, perimetre=arrondissement
        )

        dotation_commune = DotationProjetFactory(
            projet=projet_commune, dotation=DOTATION_DETR
        )
        dotation_departement = DotationProjetFactory(
            projet=projet_departement, dotation=DOTATION_DETR
        )

        prog_commune = ProgrammationProjetFactory(
            dotation_projet=dotation_commune, enveloppe=enveloppe
        )
        prog_departement = ProgrammationProjetFactory(
            dotation_projet=dotation_departement, enveloppe=enveloppe
        )

        # Test du filtre
        filterset = ProgrammationProjetFilters(
            data={"porteur": [NaturePorteurProjet.COMMUNES]}, request=mock_request
        )

        result = list(filterset.qs)
        assert prog_commune in result
        assert prog_departement not in result

    def test_cout_min_max_filter(self, mock_request, enveloppe, arrondissement):
        """Test les filtres par coût total min et max"""
        # Créer des dossiers avec différents coûts
        dossier_petit = DossierFactory(finance_cout_total=Decimal("50000.00"))
        dossier_moyen = DossierFactory(finance_cout_total=Decimal("150000.00"))
        dossier_grand = DossierFactory(finance_cout_total=Decimal("300000.00"))

        # Créer les programmations
        projet_petit = ProjetFactory(dossier_ds=dossier_petit, perimetre=arrondissement)
        projet_moyen = ProjetFactory(dossier_ds=dossier_moyen, perimetre=arrondissement)
        projet_grand = ProjetFactory(dossier_ds=dossier_grand, perimetre=arrondissement)

        dotation_petit = DotationProjetFactory(
            projet=projet_petit, dotation=DOTATION_DETR
        )
        dotation_moyen = DotationProjetFactory(
            projet=projet_moyen, dotation=DOTATION_DETR
        )
        dotation_grand = DotationProjetFactory(
            projet=projet_grand, dotation=DOTATION_DETR
        )

        prog_petit = ProgrammationProjetFactory(
            dotation_projet=dotation_petit, enveloppe=enveloppe
        )
        prog_moyen = ProgrammationProjetFactory(
            dotation_projet=dotation_moyen, enveloppe=enveloppe
        )
        prog_grand = ProgrammationProjetFactory(
            dotation_projet=dotation_grand, enveloppe=enveloppe
        )

        # Test filtre cout_min
        filterset = ProgrammationProjetFilters(
            data={"cout_min": "100000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit not in result
        assert prog_moyen in result
        assert prog_grand in result

        # Test filtre cout_max
        filterset = ProgrammationProjetFilters(
            data={"cout_max": "200000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit in result
        assert prog_moyen in result
        assert prog_grand not in result

    def test_montant_demande_min_max_filter(
        self, mock_request, enveloppe, arrondissement
    ):
        """Test les filtres par montant demandé min et max"""
        # Créer des dossiers avec différents montants demandés
        dossier_petit = DossierFactory(demande_montant=Decimal("20000.00"))
        dossier_moyen = DossierFactory(demande_montant=Decimal("80000.00"))
        dossier_grand = DossierFactory(demande_montant=Decimal("150000.00"))

        # Créer les programmations
        projet_petit = ProjetFactory(dossier_ds=dossier_petit, perimetre=arrondissement)
        projet_moyen = ProjetFactory(dossier_ds=dossier_moyen, perimetre=arrondissement)
        projet_grand = ProjetFactory(dossier_ds=dossier_grand, perimetre=arrondissement)

        dotation_petit = DotationProjetFactory(
            projet=projet_petit, dotation=DOTATION_DETR
        )
        dotation_moyen = DotationProjetFactory(
            projet=projet_moyen, dotation=DOTATION_DETR
        )
        dotation_grand = DotationProjetFactory(
            projet=projet_grand, dotation=DOTATION_DETR
        )

        prog_petit = ProgrammationProjetFactory(
            dotation_projet=dotation_petit, enveloppe=enveloppe
        )
        prog_moyen = ProgrammationProjetFactory(
            dotation_projet=dotation_moyen, enveloppe=enveloppe
        )
        prog_grand = ProgrammationProjetFactory(
            dotation_projet=dotation_grand, enveloppe=enveloppe
        )

        # Test filtre montant_demande_min
        filterset = ProgrammationProjetFilters(
            data={"montant_demande_min": "50000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit not in result
        assert prog_moyen in result
        assert prog_grand in result

        # Test filtre montant_demande_max
        filterset = ProgrammationProjetFilters(
            data={"montant_demande_max": "100000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit in result
        assert prog_moyen in result
        assert prog_grand not in result

    def test_montant_retenu_min_max_filter(
        self, mock_request, enveloppe, arrondissement
    ):
        """Test les filtres par montant retenu (programmé) min et max"""
        # Créer des programmations avec différents montants
        projet1 = ProjetFactory(perimetre=arrondissement)
        projet2 = ProjetFactory(perimetre=arrondissement)
        projet3 = ProjetFactory(perimetre=arrondissement)

        dotation1 = DotationProjetFactory(projet=projet1, dotation=DOTATION_DETR)
        dotation2 = DotationProjetFactory(projet=projet2, dotation=DOTATION_DETR)
        dotation3 = DotationProjetFactory(projet=projet3, dotation=DOTATION_DETR)

        prog_petit = ProgrammationProjetFactory(
            dotation_projet=dotation1, enveloppe=enveloppe, montant=Decimal("30000.00")
        )
        prog_moyen = ProgrammationProjetFactory(
            dotation_projet=dotation2, enveloppe=enveloppe, montant=Decimal("70000.00")
        )
        prog_grand = ProgrammationProjetFactory(
            dotation_projet=dotation3, enveloppe=enveloppe, montant=Decimal("120000.00")
        )

        # Test filtre montant_retenu_min
        filterset = ProgrammationProjetFilters(
            data={"montant_retenu_min": "50000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit not in result
        assert prog_moyen in result
        assert prog_grand in result

        # Test filtre montant_retenu_max
        filterset = ProgrammationProjetFilters(
            data={"montant_retenu_max": "80000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit in result
        assert prog_moyen in result
        assert prog_grand not in result

    def test_status_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre par statut de programmation"""
        # Créer des programmations avec différents statuts
        projet1 = ProjetFactory(perimetre=arrondissement)
        projet2 = ProjetFactory(perimetre=arrondissement)

        dotation1 = DotationProjetFactory(projet=projet1, dotation=DOTATION_DETR)
        dotation2 = DotationProjetFactory(projet=projet2, dotation=DOTATION_DETR)

        prog_accepted = ProgrammationProjetFactory(
            dotation_projet=dotation1,
            enveloppe=enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
        )
        prog_refused = ProgrammationProjetFactory(
            dotation_projet=dotation2,
            enveloppe=enveloppe,
            status=ProgrammationProjet.STATUS_REFUSED,
        )

        # Test filtre pour acceptés uniquement
        filterset = ProgrammationProjetFilters(
            data={"status": [ProgrammationProjet.STATUS_ACCEPTED]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_accepted in result
        assert prog_refused not in result

        # Test filtre pour refusés uniquement
        filterset = ProgrammationProjetFilters(
            data={"status": [ProgrammationProjet.STATUS_REFUSED]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_accepted not in result
        assert prog_refused in result

    def test_territoire_filter(
        self, mock_request, region, departement, arrondissement, enveloppe
    ):
        """Test le filtre par territoire"""
        # Créer un autre arrondissement dans le même département
        autre_arrondissement = PerimetreArrondissementFactory(
            arrondissement__departement=arrondissement.departement,
            departement=arrondissement.departement,
            region=arrondissement.region,
        )

        # Créer des projets dans différents territoires
        projet_arr1 = ProjetFactory(perimetre=arrondissement)
        projet_arr2 = ProjetFactory(perimetre=autre_arrondissement)

        dotation_projet1 = DotationProjetFactory(
            projet=projet_arr1, dotation=DOTATION_DETR
        )
        dotation_projet2 = DotationProjetFactory(
            projet=projet_arr2, dotation=DOTATION_DETR
        )

        prog_arr1 = ProgrammationProjetFactory(
            dotation_projet=dotation_projet1, enveloppe=enveloppe
        )
        prog_arr2 = ProgrammationProjetFactory(
            dotation_projet=dotation_projet2, enveloppe=enveloppe
        )

        # Test filtre par arrondissement spécifique
        filterset = ProgrammationProjetFilters(
            data={"territoire": [arrondissement.id]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_arr1 in result
        assert prog_arr2 not in result

        # Test filtre par département (doit inclure les deux arrondissements)
        filterset = ProgrammationProjetFilters(
            data={"territoire": [departement.id]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_arr1 in result
        assert prog_arr2 in result

    def test_categorie_detr_filter(
        self, mock_request, enveloppe, arrondissement, departement
    ):
        """Test le filtre par catégorie DETR"""
        # Créer des catégories DETR
        categorie1 = CategorieDetrFactory(departement=departement.departement)
        categorie2 = CategorieDetrFactory(departement=departement.departement)

        # Créer des projets avec différentes catégories
        projet1 = ProjetFactory(perimetre=arrondissement)
        projet2 = ProjetFactory(perimetre=arrondissement)

        dotation_projet1 = DotationProjetFactory(projet=projet1, dotation=DOTATION_DETR)
        dotation_projet2 = DotationProjetFactory(projet=projet2, dotation=DOTATION_DETR)

        # Associer les catégories aux dotations
        dotation_projet1.detr_categories.add(categorie1)
        dotation_projet2.detr_categories.add(categorie2)

        dotation_projet1.refresh_from_db()
        assert dotation_projet1.detr_categories.count() == 1

        prog1 = ProgrammationProjetFactory(
            dotation_projet=dotation_projet1, enveloppe=enveloppe
        )
        prog2 = ProgrammationProjetFactory(
            dotation_projet=dotation_projet2, enveloppe=enveloppe
        )

        # Test filtre par catégorie spécifique
        filterset = ProgrammationProjetFilters(
            data={"categorie_detr": [categorie1.id]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog1 in result
        assert prog2 not in result

    def test_to_notify_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre pour les projets à notifier"""
        from django.utils import timezone

        # Créer des projets avec différents états de notification
        projet1 = ProjetFactory(perimetre=arrondissement)
        projet2 = ProjetFactory(perimetre=arrondissement)
        projet3 = ProjetFactory(perimetre=arrondissement)

        dotation1 = DotationProjetFactory(projet=projet1, dotation=DOTATION_DETR)
        dotation2 = DotationProjetFactory(projet=projet2, dotation=DOTATION_DETR)
        dotation3 = DotationProjetFactory(projet=projet3, dotation=DOTATION_DETR)

        # Programmation acceptée non notifiée (à notifier)
        prog_to_notify = ProgrammationProjetFactory(
            dotation_projet=dotation1,
            enveloppe=enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            notified_at=None,
        )

        # Programmation acceptée déjà notifiée
        prog_notified = ProgrammationProjetFactory(
            dotation_projet=dotation2,
            enveloppe=enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            notified_at=timezone.now(),
        )

        # Programmation refusée
        prog_refused = ProgrammationProjetFactory(
            dotation_projet=dotation3,
            enveloppe=enveloppe,
            status=ProgrammationProjet.STATUS_REFUSED,
            notified_at=None,
        )

        # Test filtre "Notifié"
        filterset = ProgrammationProjetFilters(
            data={"notified": "yes"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_to_notify not in result
        assert prog_notified in result
        assert prog_refused in result

        # Test filtre "pas notifié"
        filterset = ProgrammationProjetFilters(
            data={"notified": "no"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_to_notify in result
        assert prog_notified not in result
        assert prog_refused not in result

    def test_order_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre de tri"""
        # Créer des programmations avec différents montants
        demandeur_a = DemandeurFactory(name="Alpha")
        demandeur_z = DemandeurFactory(name="Zulu")

        dossier_a = DossierFactory(finance_cout_total=Decimal("100000.00"))
        dossier_z = DossierFactory(finance_cout_total=Decimal("200000.00"))

        projet_a = ProjetFactory(
            dossier_ds=dossier_a, perimetre=arrondissement, demandeur=demandeur_a
        )
        projet_z = ProjetFactory(
            dossier_ds=dossier_z, perimetre=arrondissement, demandeur=demandeur_z
        )

        dotation_a = DotationProjetFactory(projet=projet_a, dotation=DOTATION_DETR)
        dotation_z = DotationProjetFactory(projet=projet_z, dotation=DOTATION_DETR)

        prog_a = ProgrammationProjetFactory(
            dotation_projet=dotation_a, enveloppe=enveloppe, montant=Decimal("50000.00")
        )
        prog_z = ProgrammationProjetFactory(
            dotation_projet=dotation_z, enveloppe=enveloppe, montant=Decimal("80000.00")
        )

        # Test tri par montant croissant
        filterset = ProgrammationProjetFilters(
            data={"order": "montant"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        # Test tri par montant décroissant
        filterset = ProgrammationProjetFilters(
            data={"order": "-montant"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

        # Test tri par cout croissant
        filterset = ProgrammationProjetFilters(
            data={"order": "cout"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        # Test tri par cout décroissant
        filterset = ProgrammationProjetFilters(
            data={"order": "-cout"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

        # Test tri par demandeur croissant
        filterset = ProgrammationProjetFilters(
            data={"order": "demandeur"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        # Test tri par demandeur décroissant
        filterset = ProgrammationProjetFilters(
            data={"order": "-demandeur"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

    def test_multiple_filters_combination(
        self, mock_request, enveloppe, arrondissement
    ):
        """Test la combinaison de plusieurs filtres"""
        nature_commune = NaturePorteurProjetFactory(type=NaturePorteurProjet.COMMUNES)

        dossier = DossierFactory(
            porteur_de_projet_nature=nature_commune,
            finance_cout_total=Decimal("150000.00"),
            demande_montant=Decimal("75000.00"),
        )

        projet = ProjetFactory(dossier_ds=dossier, perimetre=arrondissement)
        dotation = DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)

        prog_match = ProgrammationProjetFactory(
            dotation_projet=dotation,
            enveloppe=enveloppe,
            montant=Decimal("60000.00"),
            status=ProgrammationProjet.STATUS_ACCEPTED,
        )

        # Créer une programmation qui ne match pas tous les critères
        autre_dossier = DossierFactory(
            porteur_de_projet_nature=nature_commune,
            finance_cout_total=Decimal("50000.00"),  # Trop petit
        )
        autre_projet = ProjetFactory(dossier_ds=autre_dossier, perimetre=arrondissement)
        autre_dotation = DotationProjetFactory(
            projet=autre_projet, dotation=DOTATION_DETR
        )
        prog_no_match = ProgrammationProjetFactory(
            dotation_projet=autre_dotation,
            enveloppe=enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
        )

        # Test combinaison de filtres
        filterset = ProgrammationProjetFilters(
            data={
                "porteur": [NaturePorteurProjet.COMMUNES],
                "cout_min": "100000",
                "montant_retenu_min": "50000",
                "status": [ProgrammationProjet.STATUS_ACCEPTED],
            },
            request=mock_request,
        )
        result = list(filterset.qs)
        assert prog_match in result
        assert prog_no_match not in result

    def test_filterset_initialization_with_user_perimetre(
        self, mock_request, departement
    ):
        """Test l'initialisation du filterset avec les choix basés sur le périmètre utilisateur"""
        filterset = ProgrammationProjetFilters(request=mock_request)

        # Vérifier que les choix de territoire sont configurés
        territoire_choices = filterset.filters["territoire"].extra["choices"]
        assert len(territoire_choices) > 0

        # Vérifier que le périmètre de l'utilisateur est dans les choix
        perimetre_ids = [choice[0] for choice in territoire_choices]
        assert departement.id in perimetre_ids

    def test_empty_filters(self, mock_request, enveloppe, arrondissement):
        """Test que sans filtres, tous les projets de l'enveloppe sont retournés"""
        projet1 = ProjetFactory(perimetre=arrondissement)
        projet2 = ProjetFactory(perimetre=arrondissement)

        dotation1 = DotationProjetFactory(projet=projet1, dotation=DOTATION_DETR)
        dotation2 = DotationProjetFactory(projet=projet2, dotation=DOTATION_DETR)

        prog1 = ProgrammationProjetFactory(
            dotation_projet=dotation1, enveloppe=enveloppe
        )
        prog2 = ProgrammationProjetFactory(
            dotation_projet=dotation2, enveloppe=enveloppe
        )

        filterset = ProgrammationProjetFilters(request=mock_request)
        result = list(filterset.qs)

        assert prog1 in result
        assert prog2 in result

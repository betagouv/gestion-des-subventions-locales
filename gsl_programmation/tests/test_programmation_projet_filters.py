from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from django.test import RequestFactory

from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED,
)
from gsl.projet.tests.factories import (
    EnveloppeProjetFactory,
    ProjetFactory,
)
from gsl_core.tests.factories import (
    ArrondissementFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
    PersonneMoraleFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_programmation.utils.programmation_projet_filters import ProgrammationFilters


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


@pytest.fixture
def mock_request_dsil(request_factory, user):
    request = request_factory.get("/")
    request.user = user
    request.resolver_match = type(
        "MockResolverMatch", (), {"kwargs": {"dotation": DOTATION_DSIL}}
    )()
    return request


pytestmark = pytest.mark.django_db


class TestProgrammationFilters:
    def test_porteur_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre par type de porteur de projet"""
        # Créer différents types de porteurs
        nature_commune = NaturePorteurProjetFactory(type=NaturePorteurProjet.COMMUNES)
        nature_departement = NaturePorteurProjetFactory(type=NaturePorteurProjet.EPCI)

        # Créer des dossiers avec différents porteurs
        dossier_commune = DossierFactory(
            porteur_de_projet_nature=nature_commune, perimetre=arrondissement
        )
        dossier_departement = DossierFactory(
            porteur_de_projet_nature=nature_departement, perimetre=arrondissement
        )

        # Créer des projets et programmations
        projet_commune = ProjetFactory(dossier_ds=dossier_commune)
        projet_departement = ProjetFactory(dossier_ds=dossier_departement)

        prog_commune = EnveloppeProjetFactory(
            projet=projet_commune,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_departement = EnveloppeProjetFactory(
            projet=projet_departement,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test du filtre
        filterset = ProgrammationFilters(
            data={"porteur": [NaturePorteurProjet.COMMUNES]}, request=mock_request
        )

        result = list(filterset.qs)
        assert prog_commune in result
        assert prog_departement not in result

    def test_cout_min_max_filter(self, mock_request, enveloppe, arrondissement):
        """Test les filtres par coût total min et max"""
        # Créer des dossiers avec différents coûts
        dossier_petit = DossierFactory(
            finance_cout_total=Decimal("50000.00"), perimetre=arrondissement
        )
        dossier_moyen = DossierFactory(
            finance_cout_total=Decimal("150000.00"), perimetre=arrondissement
        )
        dossier_grand = DossierFactory(
            finance_cout_total=Decimal("300000.00"), perimetre=arrondissement
        )

        # Créer les programmations
        projet_petit = ProjetFactory(dossier_ds=dossier_petit)
        projet_moyen = ProjetFactory(dossier_ds=dossier_moyen)
        projet_grand = ProjetFactory(dossier_ds=dossier_grand)

        prog_petit = EnveloppeProjetFactory(
            projet=projet_petit,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_moyen = EnveloppeProjetFactory(
            projet=projet_moyen,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_grand = EnveloppeProjetFactory(
            projet=projet_grand,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test filtre cout_min
        filterset = ProgrammationFilters(
            data={"cout_min": "100000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit not in result
        assert prog_moyen in result
        assert prog_grand in result

        # Test filtre cout_max
        filterset = ProgrammationFilters(
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
        dossier_petit = DossierFactory(
            demande_montant=Decimal("20000.00"), perimetre=arrondissement
        )
        dossier_moyen = DossierFactory(
            demande_montant=Decimal("80000.00"), perimetre=arrondissement
        )
        dossier_grand = DossierFactory(
            demande_montant=Decimal("150000.00"), perimetre=arrondissement
        )

        # Créer les programmations
        projet_petit = ProjetFactory(dossier_ds=dossier_petit)
        projet_moyen = ProjetFactory(dossier_ds=dossier_moyen)
        projet_grand = ProjetFactory(dossier_ds=dossier_grand)

        prog_petit = EnveloppeProjetFactory(
            projet=projet_petit,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_moyen = EnveloppeProjetFactory(
            projet=projet_moyen,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_grand = EnveloppeProjetFactory(
            projet=projet_grand,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test filtre montant_demande_min
        filterset = ProgrammationFilters(
            data={"montant_demande_min": "50000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit not in result
        assert prog_moyen in result
        assert prog_grand in result

        # Test filtre montant_demande_max
        filterset = ProgrammationFilters(
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
        projet1 = ProjetFactory(dossier_ds__perimetre=arrondissement)
        projet2 = ProjetFactory(dossier_ds__perimetre=arrondissement)
        projet3 = ProjetFactory(dossier_ds__perimetre=arrondissement)

        prog_petit = EnveloppeProjetFactory(
            projet=projet1,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("30000.00"),
        )
        prog_moyen = EnveloppeProjetFactory(
            projet=projet2,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("70000.00"),
        )
        prog_grand = EnveloppeProjetFactory(
            projet=projet3,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("120000.00"),
        )

        # Test filtre montant_retenu_min
        filterset = ProgrammationFilters(
            data={"montant_retenu_min": "50000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit not in result
        assert prog_moyen in result
        assert prog_grand in result

        # Test filtre montant_retenu_max
        filterset = ProgrammationFilters(
            data={"montant_retenu_max": "80000"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_petit in result
        assert prog_moyen in result
        assert prog_grand not in result

    def test_status_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre par statut de programmation"""
        # Créer des programmations avec différents statuts
        projet1 = ProjetFactory(dossier_ds__perimetre=arrondissement)
        projet2 = ProjetFactory(dossier_ds__perimetre=arrondissement)

        prog_accepted = EnveloppeProjetFactory(
            projet=projet1,
            dotation=DOTATION_DETR,
            enveloppe=enveloppe,
            status=PROJET_STATUS_ACCEPTED,
        )
        prog_refused = EnveloppeProjetFactory(
            projet=projet2,
            dotation=DOTATION_DETR,
            enveloppe=enveloppe,
            status=PROJET_STATUS_REFUSED,
        )

        # Test filtre pour acceptés uniquement
        filterset = ProgrammationFilters(
            data={"status": [PROJET_STATUS_ACCEPTED]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_accepted in result
        assert prog_refused not in result

        # Test filtre pour refusés uniquement
        filterset = ProgrammationFilters(
            data={"status": [PROJET_STATUS_REFUSED]}, request=mock_request
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
        projet_arr1 = ProjetFactory(dossier_ds__perimetre=arrondissement)
        projet_arr2 = ProjetFactory(dossier_ds__perimetre=autre_arrondissement)

        prog_arr1 = EnveloppeProjetFactory(
            projet=projet_arr1,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_arr2 = EnveloppeProjetFactory(
            projet=projet_arr2,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test filtre par arrondissement spécifique
        filterset = ProgrammationFilters(
            data={"territoire": [arrondissement.id]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_arr1 in result
        assert prog_arr2 not in result

        # Test filtre par département (doit inclure les deux arrondissements)
        filterset = ProgrammationFilters(
            data={"territoire": [departement.id]}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_arr1 in result
        assert prog_arr2 in result

    def test_order_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre de tri"""
        # Créer des programmations avec différents montants
        dossier_a = DossierFactory(
            finance_cout_total=Decimal("100000.00"),
            perimetre=arrondissement,
            ds_demandeur=PersonneMoraleFactory(raison_sociale="Alpha"),
        )
        dossier_z = DossierFactory(
            finance_cout_total=Decimal("200000.00"),
            perimetre=arrondissement,
            ds_demandeur=PersonneMoraleFactory(raison_sociale="Zulu"),
        )

        projet_a = ProjetFactory(dossier_ds=dossier_a)
        projet_z = ProjetFactory(dossier_ds=dossier_z)

        prog_a = EnveloppeProjetFactory(
            projet=projet_a,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("50000.00"),
        )
        prog_z = EnveloppeProjetFactory(
            projet=projet_z,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("80000.00"),
        )

        # Test tri par montant croissant
        filterset = ProgrammationFilters(
            data={"order": "montant"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        # Test tri par montant décroissant
        filterset = ProgrammationFilters(
            data={"order": "-montant"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

        # Test tri par cout croissant
        filterset = ProgrammationFilters(data={"order": "cout"}, request=mock_request)
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        # Test tri par cout décroissant
        filterset = ProgrammationFilters(data={"order": "-cout"}, request=mock_request)
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

        # Test tri par demandeur croissant
        filterset = ProgrammationFilters(
            data={"order": "demandeur"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        # Test tri par demandeur décroissant
        filterset = ProgrammationFilters(
            data={"order": "-demandeur"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

    def test_order_by_numero_dn(self, mock_request, enveloppe, arrondissement):
        dossier_a = DossierFactory(ds_number=1000, perimetre=arrondissement)
        dossier_z = DossierFactory(ds_number=9000, perimetre=arrondissement)
        prog_a = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_a),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_z = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_z),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        filterset = ProgrammationFilters(
            data={"order": "numero_dn"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

        filterset = ProgrammationFilters(
            data={"order": "-numero_dn"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_z) < result.index(prog_a)

    def test_order_by_arrondissement(self, mock_request, enveloppe, arrondissement):
        arr_a = ArrondissementFactory(name="Alpha-Arrondissement")
        arr_z = ArrondissementFactory(name="Zulu-Arrondissement")
        dossier_a = DossierFactory(
            perimetre=arrondissement, porteur_de_projet_arrondissement=arr_a
        )
        dossier_z = DossierFactory(
            perimetre=arrondissement, porteur_de_projet_arrondissement=arr_z
        )
        prog_a = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_a),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_z = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_z),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        filterset = ProgrammationFilters(
            data={"order": "arrondissement"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

    def test_order_by_montant_sollicite(self, mock_request, enveloppe, arrondissement):
        dossier_a = DossierFactory(
            demande_montant=Decimal("10000"), perimetre=arrondissement
        )
        dossier_z = DossierFactory(
            demande_montant=Decimal("90000"), perimetre=arrondissement
        )
        prog_a = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_a),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_z = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_z),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        filterset = ProgrammationFilters(
            data={"order": "montant_sollicite"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

    def test_order_by_assiette(self, mock_request, enveloppe, arrondissement):
        dossier_a = DossierFactory(perimetre=arrondissement)
        dossier_z = DossierFactory(perimetre=arrondissement)
        prog_a = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_a),
            dotation=DOTATION_DETR,
            assiette=Decimal("50000"),
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_z = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_z),
            dotation=DOTATION_DETR,
            assiette=Decimal("200000"),
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        filterset = ProgrammationFilters(
            data={"order": "assiette"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

    def test_order_by_taux(self, mock_request, enveloppe, arrondissement):
        dossier_a = DossierFactory(perimetre=arrondissement)
        dossier_z = DossierFactory(perimetre=arrondissement)
        # prog_a: montant=10000 / assiette=100000 = 10%
        prog_a = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_a),
            dotation=DOTATION_DETR,
            assiette=Decimal("100000"),
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("10000"),
        )
        # prog_z: montant=80000 / assiette=100000 = 80%
        prog_z = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_z),
            dotation=DOTATION_DETR,
            assiette=Decimal("100000"),
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
            montant=Decimal("80000"),
        )

        filterset = ProgrammationFilters(data={"order": "taux"}, request=mock_request)
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

    def test_order_by_date_debut(self, mock_request, enveloppe, arrondissement):
        dossier_a = DossierFactory(
            perimetre=arrondissement, date_debut=date(2025, 1, 1)
        )
        dossier_z = DossierFactory(
            perimetre=arrondissement, date_debut=date(2026, 6, 1)
        )
        prog_a = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_a),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_z = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_z),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # date_debut is a date field, ascending means earliest first
        filterset = ProgrammationFilters(
            data={"order": "date_debut"}, request=mock_request
        )
        result = list(filterset.qs)
        assert result.index(prog_a) < result.index(prog_z)

    def test_multiple_filters_combination(
        self, mock_request, enveloppe, arrondissement
    ):
        """Test la combinaison de plusieurs filtres"""
        nature_commune = NaturePorteurProjetFactory(type=NaturePorteurProjet.COMMUNES)

        dossier = DossierFactory(
            porteur_de_projet_nature=nature_commune,
            finance_cout_total=Decimal("150000.00"),
            demande_montant=Decimal("75000.00"),
            perimetre=arrondissement,
        )

        projet = ProjetFactory(dossier_ds=dossier)
        prog_match = EnveloppeProjetFactory(
            projet=projet,
            dotation=DOTATION_DETR,
            enveloppe=enveloppe,
            montant=Decimal("60000.00"),
            status=PROJET_STATUS_ACCEPTED,
        )

        # Créer une programmation qui ne match pas tous les critères
        autre_dossier = DossierFactory(
            porteur_de_projet_nature=nature_commune,
            finance_cout_total=Decimal("50000.00"),  # Trop petit
            perimetre=arrondissement,
        )
        autre_projet = ProjetFactory(dossier_ds=autre_dossier)
        prog_no_match = EnveloppeProjetFactory(
            projet=autre_projet,
            dotation=DOTATION_DETR,
            enveloppe=enveloppe,
            status=PROJET_STATUS_ACCEPTED,
        )

        # Test combinaison de filtres
        filterset = ProgrammationFilters(
            data={
                "porteur": [NaturePorteurProjet.COMMUNES],
                "cout_min": "100000",
                "montant_retenu_min": "50000",
                "status": [PROJET_STATUS_ACCEPTED],
            },
            request=mock_request,
        )
        result = list(filterset.qs)
        assert prog_match in result
        assert prog_no_match not in result

    def test_filterset_territoire_queryset_with_user_perimetre(
        self, mock_request, departement
    ):
        """Le filtre territoire expose un queryset incluant le périmètre de l'utilisateur."""
        filterset = ProgrammationFilters(request=mock_request)

        territoire_queryset = filterset.form.fields["territoire"].queryset

        assert territoire_queryset.filter(id=departement.id).exists()

    def test_filterset_instantiation_does_not_query_choice_tables(self, mock_request):
        """Instantiating the filterset must not query the choice tables;
        the dropdowns evaluate their querysets lazily when the form is rendered."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            ProgrammationFilters(request=mock_request)

        executed = " ".join(q["sql"] for q in ctx.captured_queries).lower()
        for table in (
            "cofinancement",
            "projetzonage",
            "projetcontractualisation",
            "categoriedetr",
            "categoriedsil",
            "perimetre",
        ):
            assert table.lower() not in executed, (
                f"Filterset __init__ should not query {table}, got:\n"
                + "\n".join(q["sql"] for q in ctx.captured_queries)
            )

    def test_date_depot_filter(self, mock_request, enveloppe, arrondissement):
        """Test les filtres par date de dépôt"""
        dossier_ancien = DossierFactory(
            ds_date_depot=datetime(2024, 1, 15, tzinfo=timezone.utc),
            perimetre=arrondissement,
        )
        dossier_recent = DossierFactory(
            ds_date_depot=datetime(2024, 6, 15, tzinfo=timezone.utc),
            perimetre=arrondissement,
        )

        projet_ancien = ProjetFactory(dossier_ds=dossier_ancien)
        projet_recent = ProjetFactory(dossier_ds=dossier_recent)

        prog_ancien = EnveloppeProjetFactory(
            projet=projet_ancien,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_recent = EnveloppeProjetFactory(
            projet=projet_recent,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test filtre date_depot_after
        filterset = ProgrammationFilters(
            data={"date_depot_after": "2024-03-01"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_ancien not in result
        assert prog_recent in result

        # Test filtre date_depot_before
        filterset = ProgrammationFilters(
            data={"date_depot_before": "2024-03-01"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_ancien in result
        assert prog_recent not in result

        # Test boundary: dossier deposited on the cutoff date is included
        filterset = ProgrammationFilters(
            data={"date_depot_before": "2024-01-15"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_ancien in result
        assert prog_recent not in result

        # Test combinaison after + before
        filterset = ProgrammationFilters(
            data={"date_depot_after": "2024-01-01", "date_depot_before": "2024-12-31"},
            request=mock_request,
        )
        result = list(filterset.qs)
        assert prog_ancien in result
        assert prog_recent in result

    def test_date_debut_filter(self, mock_request, enveloppe, arrondissement):
        """Test les filtres par date de commencement de l'opération"""
        dossier_tot = DossierFactory(
            date_debut=date(2024, 3, 1), perimetre=arrondissement
        )
        dossier_tard = DossierFactory(
            date_debut=date(2024, 9, 1), perimetre=arrondissement
        )

        projet_tot = ProjetFactory(dossier_ds=dossier_tot)
        projet_tard = ProjetFactory(dossier_ds=dossier_tard)

        prog_tot = EnveloppeProjetFactory(
            projet=projet_tot,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_tard = EnveloppeProjetFactory(
            projet=projet_tard,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test filtre date_debut_after
        filterset = ProgrammationFilters(
            data={"date_debut_after": "2024-06-01"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_tot not in result
        assert prog_tard in result

    def test_date_achevement_filter(self, mock_request, enveloppe, arrondissement):
        """Test les filtres par date prévisionnelle d'achèvement"""
        dossier_tot = DossierFactory(
            date_achevement=date(2025, 1, 1), perimetre=arrondissement
        )
        dossier_tard = DossierFactory(
            date_achevement=date(2025, 12, 1), perimetre=arrondissement
        )

        projet_tot = ProjetFactory(dossier_ds=dossier_tot)
        projet_tard = ProjetFactory(dossier_ds=dossier_tard)

        prog_tot = EnveloppeProjetFactory(
            projet=projet_tot,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_tard = EnveloppeProjetFactory(
            projet=projet_tard,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        # Test filtre date_achevement_before
        filterset = ProgrammationFilters(
            data={"date_achevement_before": "2025-06-01"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_tot in result
        assert prog_tard not in result

    def test_search_filter(self, mock_request, enveloppe, arrondissement):
        """Test le filtre de recherche par intitulé, demandeur et n° dossier."""
        demandeur_quimper = PersonneMoraleFactory(raison_sociale="Commune de Quimper")
        demandeur_brest = PersonneMoraleFactory(raison_sociale="Commune de Brest")

        dossier_ecole = DossierFactory(
            projet_intitule="Rénovation école",
            ds_demandeur=demandeur_quimper,
            ds_number=9000001,
            perimetre=arrondissement,
        )
        dossier_mairie = DossierFactory(
            projet_intitule="Construction mairie",
            ds_demandeur=demandeur_brest,
            ds_number=9000002,
            perimetre=arrondissement,
        )

        prog_ecole = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_ecole),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog_mairie = EnveloppeProjetFactory(
            projet=ProjetFactory(dossier_ds=dossier_mairie),
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        filterset = ProgrammationFilters(data={"search": "école"}, request=mock_request)
        result = list(filterset.qs)
        assert prog_ecole in result
        assert prog_mairie not in result

        filterset = ProgrammationFilters(data={"search": "Brest"}, request=mock_request)
        result = list(filterset.qs)
        assert prog_ecole not in result
        assert prog_mairie in result

        filterset = ProgrammationFilters(
            data={"search": "9000002"}, request=mock_request
        )
        result = list(filterset.qs)
        assert prog_ecole not in result
        assert prog_mairie in result

    def test_fixed_fields_show_detr_category_on_detr_page(self, mock_request):
        """On a DETR programmation page, the DETR category sits in the fixed row
        and the DSIL category is absent."""
        filterset = ProgrammationFilters(request=mock_request)
        fixed_names = [field.name for field in filterset.fixed_fields]
        assert "categorie_detr" in fixed_names
        assert "categorie_dsil" not in fixed_names

    def test_fixed_fields_show_dsil_category_on_dsil_page(self, mock_request_dsil):
        """On a DSIL programmation page, the DSIL category sits in the fixed row
        and the DETR category is absent."""
        filterset = ProgrammationFilters(request=mock_request_dsil)
        fixed_names = [field.name for field in filterset.fixed_fields]
        assert "categorie_dsil" in fixed_names
        assert "categorie_detr" not in fixed_names

    def test_empty_filters(self, mock_request, enveloppe, arrondissement):
        """Test que sans filtres, tous les projets de l'enveloppe sont retournés"""
        projet1 = ProjetFactory(dossier_ds__perimetre=arrondissement)
        projet2 = ProjetFactory(dossier_ds__perimetre=arrondissement)

        prog1 = EnveloppeProjetFactory(
            projet=projet1,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )
        prog2 = EnveloppeProjetFactory(
            projet=projet2,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=enveloppe,
        )

        filterset = ProgrammationFilters(request=mock_request)
        result = list(filterset.qs)

        assert prog1 in result
        assert prog2 in result

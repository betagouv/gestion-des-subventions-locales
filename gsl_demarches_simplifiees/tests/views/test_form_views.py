from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    CategorieDetrFactory,
    CategorieDsilFactory,
    DossierFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db


class TestDossierSansPieceUpdateViewCategories:
    @pytest.fixture
    def user_with_perimetre(self):
        perimetre = PerimetreArrondissementFactory()
        return CollegueFactory(perimetre=perimetre)

    @pytest.fixture
    def dossier_sans_pieces(self, user_with_perimetre):
        perimetre = user_with_perimetre.perimetre
        dossier = DossierFactory(
            demande_renouvellement="REPORT SANS PIECES",
            perimetre=perimetre,
        )
        ProjetFactory(dossier_ds=dossier)
        return dossier

    def test_post_with_categories_saves_them(
        self, user_with_perimetre, dossier_sans_pieces
    ):
        dossier = dossier_sans_pieces
        demarche = dossier.ds_data.ds_demarche
        departement = dossier.projet.perimetre.departement
        cat_detr = CategorieDetrFactory(
            demarche=demarche, departement=departement, active=True
        )
        cat_dsil = CategorieDsilFactory(demarche=demarche, active=True)

        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier.pk])

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR, DOTATION_DSIL],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
            "demande_categorie_detr": cat_detr.pk,
            "demande_categorie_dsil": cat_dsil.pk,
        }

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ):
            response = client.post(url, data=form_data)

        assert response.status_code == 302
        dossier.refresh_from_db()
        assert dossier.demande_categorie_detr == cat_detr
        assert dossier.demande_categorie_dsil == cat_dsil


class TestDossierSansPieceUpdateView:
    @pytest.fixture
    def user_with_perimetre(self):
        perimetre = PerimetreArrondissementFactory()
        return CollegueFactory(perimetre=perimetre)

    @pytest.fixture
    def dossier_sans_pieces(self, user_with_perimetre):
        perimetre = user_with_perimetre.perimetre
        dossier = DossierFactory(
            demande_renouvellement="REPORT SANS PIECES",
            perimetre=perimetre,
        )
        ProjetFactory(dossier_ds=dossier)
        return dossier

    def test_view_get_accessible_for_user_with_perimeter(
        self, user_with_perimetre, dossier_sans_pieces
    ):
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier_sans_pieces.pk])
        response = client.get(url)

        assert response.status_code == 200
        assert "form" in response.context

    def test_view_not_accessible_for_dossier_not_sans_pieces(self, user_with_perimetre):
        perimetre = user_with_perimetre.perimetre
        dossier = DossierFactory(
            demande_renouvellement="NOUVELLE DEMANDE",
            perimetre=perimetre,
        )
        ProjetFactory(dossier_ds=dossier)

        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier.pk])
        response = client.get(url)

        assert response.status_code == 404

    def test_view_not_accessible_outside_perimeter(self, user_with_perimetre):
        other_perimetre = PerimetreArrondissementFactory()
        dossier = DossierFactory(
            demande_renouvellement="REPORT SANS PIECES",
            perimetre=other_perimetre,
        )
        ProjetFactory(dossier_ds=dossier)

        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier.pk])
        response = client.get(url)

        assert response.status_code == 404

    def test_view_post_success_redirects_to_projet(
        self, user_with_perimetre, dossier_sans_pieces
    ):
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier_sans_pieces.pk])

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
        }

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ):
            response = client.post(url, data=form_data)

        assert response.status_code == 302
        expected_redirect = reverse(
            "gsl_projet:get-projet", args=[dossier_sans_pieces.projet.pk]
        )
        assert response.url == expected_redirect

    def test_view_post_success_updates_dossier(
        self, user_with_perimetre, dossier_sans_pieces
    ):
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier_sans_pieces.pk])

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "150000.00",
            "demande_montant": "75000.00",
        }

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ):
            client.post(url, data=form_data)

        dossier_sans_pieces.refresh_from_db()
        assert DOTATION_DETR in dossier_sans_pieces.demande_dispositif_sollicite
        assert dossier_sans_pieces.finance_cout_total == Decimal("150000.00")
        assert dossier_sans_pieces.demande_montant == Decimal("75000.00")

    def test_view_post_invalid_data_returns_form_with_errors(
        self, user_with_perimetre, dossier_sans_pieces
    ):
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier_sans_pieces.pk])

        form_data = {
            "demande_dispositif_sollicite": [],
            "finance_cout_total": "",
            "demande_montant": "",
        }

        response = client.post(url, data=form_data)

        assert response.status_code == 200
        assert "form" in response.context
        form = response.context["form"]
        assert not form.is_valid()
        assert "demande_dispositif_sollicite" in form.errors

    def test_view_not_accessible_for_anonymous_user(self, dossier_sans_pieces):
        from django.test import Client

        client = Client()
        url = reverse("ds:dossier-sans-piece-update", args=[dossier_sans_pieces.pk])
        response = client.get(url)

        assert response.status_code == 302
        assert "login" in response.url

    def test_view_accessible_for_staff_user_without_perimetre(
        self, dossier_sans_pieces
    ):
        staff_user = CollegueFactory(is_staff=True, perimetre=None)
        client = ClientWithLoggedUserFactory(user=staff_user)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier_sans_pieces.pk])
        response = client.get(url)

        assert response.status_code == 200

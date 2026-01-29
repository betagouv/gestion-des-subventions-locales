from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.forms import (
    DossierReporteSansPieceForm,
    DotationFormField,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.constants import DOTATION_CHOICES, DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db


class TestDotationFormField:
    def test_dotation_form_field_choices(self):
        field = DotationFormField()
        assert list(field.choices) == list(DOTATION_CHOICES)

    def test_dotation_form_field_prepare_value_with_detr(self):
        field = DotationFormField()
        result = field.prepare_value(DOTATION_DETR)
        assert result == [DOTATION_DETR]

    def test_dotation_form_field_prepare_value_with_dsil(self):
        field = DotationFormField()
        result = field.prepare_value(DOTATION_DSIL)
        assert result == [DOTATION_DSIL]

    def test_dotation_form_field_prepare_value_with_both_dotations(self):
        field = DotationFormField()
        result = field.prepare_value(f"{DOTATION_DETR}, {DOTATION_DSIL}")
        assert DOTATION_DETR in result
        assert DOTATION_DSIL in result
        assert len(result) == 2

    def test_dotation_form_field_prepare_value_with_empty_string(self):
        field = DotationFormField()
        result = field.prepare_value("")
        assert result == []

    def test_dotation_form_field_prepare_value_with_list(self):
        field = DotationFormField()
        result = field.prepare_value([DOTATION_DETR, DOTATION_DSIL])
        assert DOTATION_DETR in result
        assert DOTATION_DSIL in result


class TestDossierReporteSansPieceForm:
    def test_form_valid_with_detr(self):
        dossier = DossierFactory()
        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

    def test_form_valid_with_dsil(self):
        dossier = DossierFactory()
        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DSIL],
            "finance_cout_total": "200000.00",
            "demande_montant": "80000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

    def test_form_valid_with_double_dotation(self):
        dossier = DossierFactory()
        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR, DOTATION_DSIL],
            "finance_cout_total": "150000.00",
            "demande_montant": "75000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

    def test_form_invalid_missing_dispositif_sollicite(self):
        dossier = DossierFactory()
        form_data = {
            "demande_dispositif_sollicite": [],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert not form.is_valid()
        assert "demande_dispositif_sollicite" in form.errors

    def test_form_invalid_missing_finance_cout_total(self):
        dossier = DossierFactory()
        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "",
            "demande_montant": "50000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert not form.is_valid()
        assert "finance_cout_total" in form.errors

    def test_form_invalid_missing_demande_montant(self):
        dossier = DossierFactory()
        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert not form.is_valid()
        assert "demande_montant" in form.errors

    def test_form_invalid_missing_all_fields(self):
        dossier = DossierFactory()
        form_data = {}
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert not form.is_valid()
        assert "demande_dispositif_sollicite" in form.errors
        assert "finance_cout_total" in form.errors
        assert "demande_montant" in form.errors

    def test_form_save_updates_dossier_fields(self):
        dossier = DossierFactory(
            demande_dispositif_sollicite="",
            finance_cout_total=None,
            demande_montant=None,
        )
        ProjetFactory(dossier_ds=dossier)

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ):
            saved_dossier = form.save()

        saved_dossier.refresh_from_db()
        assert DOTATION_DETR in saved_dossier.demande_dispositif_sollicite
        assert saved_dossier.finance_cout_total == Decimal("100000.00")
        assert saved_dossier.demande_montant == Decimal("50000.00")

    def test_form_save_calls_dotation_projet_service(self):
        dossier = DossierFactory()
        projet = ProjetFactory(dossier_ds=dossier)

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ) as mock_service:
            form.save()
            mock_service.assert_called_once_with(projet)

    def test_form_save_with_double_dotation_updates_dispositif(self):
        dossier = DossierFactory(demande_dispositif_sollicite="")
        ProjetFactory(dossier_ds=dossier)

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR, DOTATION_DSIL],
            "finance_cout_total": "200000.00",
            "demande_montant": "100000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ):
            saved_dossier = form.save()

        saved_dossier.refresh_from_db()
        assert DOTATION_DETR in saved_dossier.demande_dispositif_sollicite
        assert DOTATION_DSIL in saved_dossier.demande_dispositif_sollicite


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
            porteur_de_projet_arrondissement__core_arrondissement=perimetre.arrondissement,
        )
        ProjetFactory(dossier_ds=dossier, perimetre=perimetre)
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
            porteur_de_projet_arrondissement__core_arrondissement=perimetre.arrondissement,
        )
        ProjetFactory(dossier_ds=dossier, perimetre=perimetre)

        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("ds:dossier-sans-piece-update", args=[dossier.pk])
        response = client.get(url)

        assert response.status_code == 404

    def test_view_not_accessible_outside_perimeter(self, user_with_perimetre):
        other_perimetre = PerimetreArrondissementFactory()
        dossier = DossierFactory(
            demande_renouvellement="REPORT SANS PIECES",
            porteur_de_projet_arrondissement__core_arrondissement=other_perimetre.arrondissement,
        )
        ProjetFactory(dossier_ds=dossier, perimetre=other_perimetre)

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

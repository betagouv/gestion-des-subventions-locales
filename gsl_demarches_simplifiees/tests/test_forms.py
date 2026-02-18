from decimal import Decimal
from unittest.mock import patch

import pytest

from gsl_demarches_simplifiees.forms import (
    DossierReporteSansPieceForm,
    DotationFormField,
)
from gsl_demarches_simplifiees.tests.factories import (
    CategorieDetrFactory,
    CategorieDsilFactory,
    DossierFactory,
)
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


class TestDossierReporteSansPieceFormCategories:
    @pytest.fixture
    def dossier_with_projet(self):
        dossier = DossierFactory()
        ProjetFactory(dossier_ds=dossier)
        return dossier

    def test_form_valid_with_detr_category(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        departement = dossier.projet.perimetre.departement
        cat_detr = CategorieDetrFactory(
            demarche=demarche, departement=departement, active=True
        )

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
            "demande_categorie_detr": cat_detr.pk,
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

    def test_form_valid_with_dsil_category(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        cat_dsil = CategorieDsilFactory(demarche=demarche, active=True)

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DSIL],
            "finance_cout_total": "200000.00",
            "demande_montant": "80000.00",
            "demande_categorie_dsil": cat_dsil.pk,
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

    def test_form_valid_with_both_categories(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        departement = dossier.projet.perimetre.departement
        cat_detr = CategorieDetrFactory(
            demarche=demarche, departement=departement, active=True
        )
        cat_dsil = CategorieDsilFactory(demarche=demarche, active=True)

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR, DOTATION_DSIL],
            "finance_cout_total": "150000.00",
            "demande_montant": "75000.00",
            "demande_categorie_detr": cat_detr.pk,
            "demande_categorie_dsil": cat_dsil.pk,
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

    def test_form_valid_without_categories(self, dossier_with_projet):
        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR],
            "finance_cout_total": "100000.00",
            "demande_montant": "50000.00",
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier_with_projet)
        assert form.is_valid(), form.errors

    def test_save_persists_categories(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        departement = dossier.projet.perimetre.departement
        cat_detr = CategorieDetrFactory(
            demarche=demarche, departement=departement, active=True
        )
        cat_dsil = CategorieDsilFactory(demarche=demarche, active=True)

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DETR, DOTATION_DSIL],
            "finance_cout_total": "150000.00",
            "demande_montant": "75000.00",
            "demande_categorie_detr": cat_detr.pk,
            "demande_categorie_dsil": cat_dsil.pk,
        }
        form = DossierReporteSansPieceForm(data=form_data, instance=dossier)
        assert form.is_valid(), form.errors

        with patch(
            "gsl_demarches_simplifiees.forms.DotationProjetService.create_or_update_dotation_projet_from_projet"
        ):
            saved_dossier = form.save()

        saved_dossier.refresh_from_db()
        assert saved_dossier.demande_categorie_detr == cat_detr
        assert saved_dossier.demande_categorie_dsil == cat_dsil

    def test_save_clears_detr_category_when_detr_unchecked(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        departement = dossier.projet.perimetre.departement
        cat_detr = CategorieDetrFactory(
            demarche=demarche, departement=departement, active=True
        )
        dossier.demande_categorie_detr = cat_detr
        dossier.save()

        form_data = {
            "demande_dispositif_sollicite": [DOTATION_DSIL],
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
        assert saved_dossier.demande_categorie_detr is None

    def test_save_clears_dsil_category_when_dsil_unchecked(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        cat_dsil = CategorieDsilFactory(demarche=demarche, active=True)
        dossier.demande_categorie_dsil = cat_dsil
        dossier.save()

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
        assert saved_dossier.demande_categorie_dsil is None

    def test_detr_queryset_filtered_by_demarche_and_departement(
        self, dossier_with_projet
    ):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche
        departement = dossier.projet.perimetre.departement

        matching_cat = CategorieDetrFactory(
            demarche=demarche, departement=departement, active=True
        )
        # Different demarche
        CategorieDetrFactory(departement=departement, active=True)
        # Different departement
        CategorieDetrFactory(demarche=demarche, active=True)
        # Inactive
        CategorieDetrFactory(demarche=demarche, departement=departement, active=False)

        form = DossierReporteSansPieceForm(instance=dossier)
        detr_qs = form.fields["demande_categorie_detr"].queryset
        assert list(detr_qs) == [matching_cat]

    def test_dsil_queryset_filtered_by_demarche(self, dossier_with_projet):
        dossier = dossier_with_projet
        demarche = dossier.ds_demarche

        matching_cat = CategorieDsilFactory(demarche=demarche, active=True)
        # Different demarche
        CategorieDsilFactory(active=True)
        # Inactive
        CategorieDsilFactory(demarche=demarche, active=False)

        form = DossierReporteSansPieceForm(instance=dossier)
        dsil_qs = form.fields["demande_categorie_dsil"].queryset
        assert list(dsil_qs) == [matching_cat]

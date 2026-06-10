from unittest import mock

import pytest
from django.contrib import admin

from gsl_demarches_simplifiees.admin import DossierAdmin
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory


@pytest.fixture
def dossier_admin():
    return DossierAdmin(Dossier, admin.site)


@pytest.mark.django_db
def test_refresh_from_db_small_queryset_uses_high_priority(dossier_admin, rf):
    DossierFactory.create_batch(3)
    queryset = Dossier.objects.all()

    with mock.patch(
        "gsl_demarches_simplifiees.admin.task_refresh_dossier_from_saved_data.apply_async"
    ) as mock_apply:
        dossier_admin.refresh_from_db(rf.get("/"), queryset)

    assert mock_apply.call_count == 3
    for call in mock_apply.call_args_list:
        assert call.kwargs["priority"] == 0


@pytest.mark.django_db
def test_refresh_from_db_mass_queryset_uses_low_priority(dossier_admin, rf):
    DossierFactory.create_batch(10)
    queryset = Dossier.objects.all()

    with mock.patch(
        "gsl_demarches_simplifiees.admin.task_refresh_dossier_from_saved_data.apply_async"
    ) as mock_apply:
        dossier_admin.refresh_from_db(rf.get("/"), queryset)

    assert mock_apply.call_count == 10
    for call in mock_apply.call_args_list:
        assert call.kwargs["priority"] == 9


@pytest.mark.django_db
def test_refresh_from_ds_small_queryset_uses_high_priority(dossier_admin, rf):
    DossierFactory.create_batch(3)
    queryset = Dossier.objects.all()

    with mock.patch(
        "gsl_demarches_simplifiees.admin.task_save_one_dossier_from_ds.apply_async"
    ) as mock_apply:
        dossier_admin.refresh_from_ds(rf.get("/"), queryset)

    assert mock_apply.call_count == 3
    for call in mock_apply.call_args_list:
        assert call.kwargs["priority"] == 0


@pytest.mark.django_db
def test_refresh_from_ds_mass_queryset_uses_low_priority(dossier_admin, rf):
    DossierFactory.create_batch(10)
    queryset = Dossier.objects.all()

    with mock.patch(
        "gsl_demarches_simplifiees.admin.task_save_one_dossier_from_ds.apply_async"
    ) as mock_apply:
        dossier_admin.refresh_from_ds(rf.get("/"), queryset)

    assert mock_apply.call_count == 10
    for call in mock_apply.call_args_list:
        assert call.kwargs["priority"] == 9

from unittest import mock

import pytest

from gsl_demarches_simplifiees.tasks import task_refresh_every_demarche
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory


@pytest.mark.django_db
def test_refresh_every_demarche_uses_high_priority_for_small_batch():
    DemarcheFactory.create_batch(3)

    with mock.patch(
        "gsl_demarches_simplifiees.tasks.task_save_demarche_from_ds.apply_async"
    ) as mock_apply:
        task_refresh_every_demarche()

    assert mock_apply.call_count == 3
    for call in mock_apply.call_args_list:
        assert call.kwargs["priority"] == 0


@pytest.mark.django_db
def test_refresh_every_demarche_uses_low_priority_for_mass_batch():
    DemarcheFactory.create_batch(10)

    with mock.patch(
        "gsl_demarches_simplifiees.tasks.task_save_demarche_from_ds.apply_async"
    ) as mock_apply:
        task_refresh_every_demarche()

    assert mock_apply.call_count == 10
    for call in mock_apply.call_args_list:
        assert call.kwargs["priority"] == 9

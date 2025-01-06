from unittest import mock

import pytest

import gsl_projet.signals as projet_signals  # noqa F401
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

pytestmark = pytest.mark.django_db


def test_dont_create_projets_from_incomplete_data():
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        DossierFactory(ds_state=Dossier.STATE_EN_CONSTRUCTION)
        task_mock.assert_not_called()
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        DossierFactory(ds_state="")
        task_mock.assert_not_called()
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        dossier = DossierFactory(ds_state=Dossier.STATE_EN_INSTRUCTION)
        task_mock.assert_called_once_with(dossier.ds_number)

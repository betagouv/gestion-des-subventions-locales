from unittest import mock

import pytest

from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.tasks import (
    create_all_projets_from_dossiers,
)

pytestmark = pytest.mark.django_db


def test_create_all_projets():
    DossierFactory(ds_state=Dossier.STATE_EN_CONSTRUCTION)
    dossier_en_instruction = DossierFactory(ds_state=Dossier.STATE_EN_INSTRUCTION)
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        create_all_projets_from_dossiers()
        task_mock.assert_called_once_with(dossier_en_instruction.ds_number)

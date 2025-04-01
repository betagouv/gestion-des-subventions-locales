import pytest
from django.db import IntegrityError

from gsl_projet.constants import DOTATIONS
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.mark.parametrize(("dotation"), DOTATIONS)
@pytest.mark.django_db
def test_dotation_projet_unicity(dotation):
    projet = ProjetFactory()
    with pytest.raises(IntegrityError):
        DotationProjetFactory.create_batch(2, projet=projet, dotation=dotation)

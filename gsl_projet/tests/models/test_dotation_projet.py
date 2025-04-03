import pytest
from django.db import IntegrityError
from django.forms import ValidationError

from gsl_projet.constants import DOTATION_DSIL, DOTATIONS
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.mark.parametrize(("dotation"), DOTATIONS)
@pytest.mark.django_db
def test_dotation_projet_unicity(dotation):
    projet = ProjetFactory()
    with pytest.raises(IntegrityError):
        DotationProjetFactory.create_batch(2, projet=projet, dotation=dotation)


@pytest.mark.django_db
def test_dsil_dotation_projet_must_have_a_detr_avis_commission_null():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL, detr_avis_commission=True
    )
    with pytest.raises(ValidationError) as exc_info:
        dotation_projet.full_clean()

    assert exc_info.value.message_dict["detr_avis_commission"][0] == (
        "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
    )

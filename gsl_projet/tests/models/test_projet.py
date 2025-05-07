import pytest

from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    ("create_a_detr_projet", "create_a_dsil_projet", "expected_is_asking_for_detr"),
    (
        (True, False, True),
        (True, True, True),
        (False, True, False),
    ),
)
def test_is_asking_for_detr(
    create_a_detr_projet, create_a_dsil_projet, expected_is_asking_for_detr
):
    projet = ProjetFactory()
    if create_a_detr_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    if create_a_dsil_projet:
        DotationProjetFactory(projet=projet, dotation=DOTATION_DSIL)

    assert projet.is_asking_for_detr is expected_is_asking_for_detr

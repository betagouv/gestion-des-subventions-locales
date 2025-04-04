import pytest
from django.db import IntegrityError
from django.forms import ValidationError

from gsl_projet.constants import DOTATION_DSIL, DOTATIONS
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.mark.parametrize(("dotation"), DOTATIONS)
@pytest.mark.django_db
def test_dotation_projet_unicity(dotation):
    projet = ProjetFactory()
    DotationProjet(projet=projet, dotation=dotation).save()
    with pytest.raises(IntegrityError):
        DotationProjet(projet=projet, dotation=dotation).save()


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


@pytest.mark.django_db
def test_assiette_or_cout_total():
    dotation_projet = DotationProjetFactory(
        assiette=1_000, projet__dossier_ds__finance_cout_total=2_000
    )
    assert dotation_projet.assiette_or_cout_total == 1_000

    dotation_projet = DotationProjetFactory(
        assiette=None, projet__dossier_ds__finance_cout_total=2_000
    )
    assert dotation_projet.assiette_or_cout_total == 2_000

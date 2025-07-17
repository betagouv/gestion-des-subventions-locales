import io

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_notification.utils import (
    get_modele_perimetres,
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)


def test_update_file_name_to_put_it_in_a_programmation_projet_folder():
    # Simulate a file-like object with a 'name' attribute
    class DummyFile(io.BytesIO):
        def __init__(self, name):
            super().__init__()
            self.name = name

    file = DummyFile("document.pdf")
    programmation_projet_id = 42

    update_file_name_to_put_it_in_a_programmation_projet_folder(
        file, programmation_projet_id
    )

    assert file.name == "programmation_projet_42/document.pdf"


@pytest.mark.django_db
def test_get_modele_perimetres():
    arrondissement_11 = PerimetreArrondissementFactory()
    departement_1 = PerimetreDepartementalFactory(
        departement=arrondissement_11.departement, region=arrondissement_11.region
    )
    region = PerimetreRegionalFactory(region=departement_1.region)
    arrondissement_12 = PerimetreArrondissementFactory(
        arrondissement__departement=departement_1.departement,
        departement=departement_1.departement,
        region=region.region,
    )

    departement_2 = PerimetreDepartementalFactory(
        departement__region=region.region, region=region.region
    )
    _arrondissement_21 = PerimetreArrondissementFactory(
        arrondissement__departement=departement_2.departement,
        region=region.region,
        departement=departement_2.departement,
    )

    assert get_modele_perimetres("DETR", arrondissement_11) == [
        arrondissement_11,
        departement_1,
    ]
    assert get_modele_perimetres("DETR", departement_1) == [departement_1]
    with pytest.raises(ValueError) as exc_info:
        assert get_modele_perimetres("DETR", region) == [region]
    assert str(exc_info.value) == (
        "Les modèles de la dotation DETR ne sont pas accessibles pour les utilisateurs dont le périmètre n'est pas de type arrondissement ou départemental."
    )

    assert get_modele_perimetres("DSIL", arrondissement_12) == [
        arrondissement_12,
        departement_1,
        region,
    ]
    assert get_modele_perimetres("DSIL", departement_1) == [departement_1, region]
    assert get_modele_perimetres("DSIL", region) == [region]

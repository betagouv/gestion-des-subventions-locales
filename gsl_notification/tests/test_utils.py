import datetime
import io
import os

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.tests.factories import PersonneMoraleFactory
from gsl_notification.tests.factories import AnnexeFactory
from gsl_notification.utils import (
    get_modele_perimetres,
    replace_mentions_in_html,
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory


@pytest.fixture
def programmation_projet():
    perimetre = PerimetreDepartementalFactory(
        departement__name="Haute-Garonne",
    )
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__ds_demandeur=PersonneMoraleFactory(
            raison_sociale="Commune de Bagnères-de-Luchon"
        ),
        dotation_projet__projet__dossier_ds__projet_intitule="Nouvelle plaque d'égoûts",
        dotation_projet__projet__perimetre=perimetre,
        dotation_projet__projet__dossier_ds__date_debut=datetime.date(1998, 7, 12),
        dotation_projet__projet__dossier_ds__date_achevement=datetime.date(2024, 7, 31),
        montant=2_000.50,
        dotation_projet__assiette=20_000,
    )


@pytest.mark.parametrize(
    "id, label, expected_value",
    (
        (1, "Nom du bénéficiaire", "Commune de Bagnères-de-Luchon"),
        (2, "Intitulé du projet", "Nouvelle plaque d'égoûts"),
        (3, "Nom du département", "Haute-Garonne"),
        (4, "Montant prévisionnel de la subvention", "2 000,50 €"),
        (5, "Taux de subvention", "10,002 %"),
        (6, "Date de commencement", "12/07/1998"),
        (7, "Date d'achèvement", "31/07/2024"),
    ),
)
@pytest.mark.django_db
def test_replace_mentions_in_html(id, label, expected_value, programmation_projet):
    html_content = f'<p>Voici le mot: <span class="mention" data-type="mention" data-id="{id}" data-label="{label}" data-mention-suggestion-char="@">@{label}</span> vous octroie une subvention</p><p>Bravo et merci !</p>'
    expected_text = f"<p>Voici le mot: {expected_value} vous octroie une subvention</p><p>Bravo et merci !</p>"

    assert expected_text == replace_mentions_in_html(html_content, programmation_projet)


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
def test_update_file_name_to_put_it_in_a_programmation_projet_folder_with_annexe():
    pp = ProgrammationProjetFactory()
    annexe = AnnexeFactory(programmation_projet=pp)
    assert pp.annexes.count() == 1

    class DummyFile(io.BytesIO):
        def __init__(self, name):
            super().__init__()
            self.name = name

    file_name = annexe.name
    base_name, _extension = os.path.splitext(file_name)
    file_2 = DummyFile(file_name)

    update_file_name_to_put_it_in_a_programmation_projet_folder(
        file_2, pp.id, is_annexe=True
    )

    assert file_2.name == f"programmation_projet_{pp.id}/{base_name}_2.pdf"


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

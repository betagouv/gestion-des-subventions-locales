import pytest

from gsl_core.models import Arrondissement
from gsl_core.tests.factories import (
    AdresseFactory,
    CommuneFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    PersonneMoraleFactory,
)

from ..models import Projet

pytestmark = pytest.mark.django_db(transaction=True)


def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    assert dossier.porteur_de_projet_arrondissement is not None
    assert dossier.ds_demandeur.address.commune.arrondissement is not None

    projet = Projet.get_or_create_from_ds_dossier(dossier)

    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse

    # two arrondissements (provided via user input and insee), use insee in that case
    assert projet.demandeur is not None
    assert isinstance(projet.demandeur.arrondissement, Arrondissement)
    assert (
        projet.demandeur.arrondissement
        == dossier.ds_demandeur.address.commune.arrondissement
    )
    other_projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert other_projet == projet


def test_dossier_without_ds_arrondissement_uses_demandeur_arrondissement():
    dossier = DossierFactory(
        projet_adresse=AdresseFactory(), porteur_de_projet_arrondissement=None
    )
    assert dossier.porteur_de_projet_arrondissement is None
    projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert isinstance(projet.demandeur.arrondissement, Arrondissement)
    assert (
        projet.demandeur.arrondissement
        == dossier.ds_demandeur.address.commune.arrondissement
    )


def test_dossier_without_demandeur_arrondissement_uses_ds_arrondissement():
    dossier = DossierFactory(
        ds_demandeur=PersonneMoraleFactory(
            address=AdresseFactory(commune=CommuneFactory(arrondissement=None))
        )
    )
    assert dossier.ds_demandeur.address.commune.arrondissement is None
    assert dossier.porteur_de_projet_arrondissement is not None
    projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert isinstance(projet.demandeur.arrondissement, Arrondissement)
    assert (
        projet.demandeur.arrondissement
        == dossier.porteur_de_projet_arrondissement.core_arrondissement
    )


# déjà testé : arrondissement DS non renseigné

# arrondissement_ds sans arrondissement_insee : tester que ça plante pas ; tester que l'info retenue à la fin est correcte

# commune sans département :> rare :> besoin de tester ? => on veut pas que ça plante bêtement ; mais on est un peu coincés qd même niveau fonctionnel

# commune sans arrondissement => cas très fréquent surtout en prod => déjà testé que ça plante pas
#

from datetime import datetime
from typing import TYPE_CHECKING

from gsl.historique.models import ProjetAction
from gsl.projet.constants import (
    DS_TRAITEMENT_EVENT_ACCEPTE,
    DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE,
    DS_TRAITEMENT_EVENT_DEPOSE,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION,
    DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_REFUSE,
    DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT,
    DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION,
    DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION,
)

if TYPE_CHECKING:
    from gsl.projet.models import Projet


def create_projet_actions_from_dossier_traitements(projet: "Projet") -> int:
    """Parcourt tous les traitements DN du dossier et crée les
    ProjetActions manquantes (dépôt, passage en instruction, retour en
    instruction, retour en construction, notification), en associant
    `source_id` (id du Traitement DN) qui sert de clé pour ne jamais
    créer de doublon si la fonction est rejouée (ex : resynchronisation
    périodique du dossier). Retourne le nombre de ProjetActions créées."""
    event_to_action_type = {
        DS_TRAITEMENT_EVENT_DEPOSE: ProjetAction.TYPE_DEPOT_DOSSIER,
        DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION: ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT: ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION: ProjetAction.TYPE_RETOUR_EN_INSTRUCTION,
        DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION: ProjetAction.TYPE_RETOUR_EN_CONSTRUCTION,
        DS_TRAITEMENT_EVENT_ACCEPTE: ProjetAction.TYPE_NOTIFIED,
        DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT: ProjetAction.TYPE_NOTIFIED,
        DS_TRAITEMENT_EVENT_REFUSE: ProjetAction.TYPE_NOTIFIED,
        DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT: ProjetAction.TYPE_NOTIFIED,
        DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE: ProjetAction.TYPE_NOTIFIED,
    }

    traitements = projet.dossier_ds.traitements

    created_count = 0
    for traitement in traitements:
        action_type = event_to_action_type.get(traitement.get("event"))
        traitement_id = traitement.get("id")
        date_traitement = traitement.get("dateTraitement")
        if not action_type or not traitement_id or not date_traitement:
            continue

        _, created = ProjetAction.objects.get_or_create(
            projet=projet,
            source_id=traitement_id,
            defaults={
                "action_type": action_type,
                "source": ProjetAction.SOURCE_DN,
                "created_at": datetime.fromisoformat(date_traitement),
            },
        )
        created_count += created

    return created_count

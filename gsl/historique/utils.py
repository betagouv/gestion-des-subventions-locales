from datetime import datetime
from typing import TYPE_CHECKING

from gsl.core.models import Collegue
from gsl.historique.models import ProjetAction
from gsl_demarches_simplifiees.models import Dossier

if TYPE_CHECKING:
    from gsl.projet.models import Projet


def get_or_create_collegue_from_traitement_email(
    traitement: dict | None,
) -> Collegue | None:
    if not traitement:
        return None
    email = (traitement.get("emailAgentTraitant") or "").strip().lower()
    if not email:
        return None

    return Collegue.objects.get_or_create_from_email(email)


def create_projet_actions_from_dossier_traitements(projet: "Projet") -> int:
    """Parcourt tous les traitements DN du dossier et crée les
    ProjetActions manquantes (dépôt, passage en instruction, retour en
    instruction, retour en construction, notification), en associant
    `source_id` (id du Traitement DN) qui sert de clé pour ne jamais
    créer de doublon si la fonction est rejouée (ex : resynchronisation
    périodique du dossier). Retourne le nombre de ProjetActions créées."""
    event = Dossier.TraitementEvent
    event_to_action_type = {
        event.DEPOSE: ProjetAction.TYPE_DEPOT_DOSSIER,
        event.PASSE_EN_INSTRUCTION: ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        event.PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT: ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
        event.REPASSE_EN_INSTRUCTION: ProjetAction.TYPE_RETOUR_EN_INSTRUCTION,
        event.REPASSE_EN_CONSTRUCTION: ProjetAction.TYPE_RETOUR_EN_CONSTRUCTION,
        event.ACCEPTE: ProjetAction.TYPE_NOTIFIED,
        event.ACCEPTE_AUTOMATIQUEMENT: ProjetAction.TYPE_NOTIFIED,
        event.REFUSE: ProjetAction.TYPE_NOTIFIED,
        event.REFUSE_AUTOMATIQUEMENT: ProjetAction.TYPE_NOTIFIED,
        event.CLASSE_SANS_SUITE: ProjetAction.TYPE_NOTIFIED,
    }

    traitements = projet.dossier_ds.traitements

    created_count = 0
    for traitement in traitements:
        action_type = event_to_action_type.get(traitement.get("event"))
        traitement_id = traitement.get("id")
        date_traitement = traitement.get("dateTraitement")
        details = traitement.get("motivation")
        if not action_type or not traitement_id or not date_traitement:
            continue

        _, created = ProjetAction.objects.get_or_create(
            projet=projet,
            source_id=traitement_id,
            defaults={
                "action_type": action_type,
                "source": ProjetAction.SOURCE_DN,
                "created_at": datetime.fromisoformat(date_traitement),
                "actor": get_or_create_collegue_from_traitement_email(traitement),
                "details": details or "",
            },
        )
        created_count += created

    return created_count

from typing import Literal

# TODO move this file in gsl/core

DOTATION_DETR = "DETR"
DOTATION_DSIL = "DSIL"
DOTATIONS = (DOTATION_DETR, DOTATION_DSIL)
DOTATION_CHOICES = ((DOTATION_DETR, DOTATION_DETR), (DOTATION_DSIL, DOTATION_DSIL))

# TYPE
POSSIBLE_DOTATIONS = Literal["DETR", "DSIL"]

PROJET_STATUS_ACCEPTED = "accepted"
PROJET_STATUS_REFUSED = "refused"
PROJET_STATUS_PROCESSING = "processing"
PROJET_STATUS_DISMISSED = "dismissed"
PROJET_STATUS_CHOICES = (
    (PROJET_STATUS_ACCEPTED, "✅ Accepté"),
    (PROJET_STATUS_REFUSED, "❌ Refusé"),
    (PROJET_STATUS_PROCESSING, "🔄 En traitement"),
    (PROJET_STATUS_DISMISSED, "⛔️ Classé sans suite"),
)
PROJET_FINAL_STATUSES = [
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED,
    PROJET_STATUS_DISMISSED,
]

NOTIFICATION_STATUS_TO_GENERATE = "to_generate"
NOTIFICATION_STATUS_TO_SIGN = "to_sign"
NOTIFICATION_STATUS_TO_NOTIFY = "to_notify"
NOTIFICATION_STATUS_NOTIFIED = "notified"
NOTIFICATION_STATUS_CHOICES = (
    (NOTIFICATION_STATUS_TO_GENERATE, "À générer"),
    (NOTIFICATION_STATUS_TO_SIGN, "À signer"),
    (NOTIFICATION_STATUS_TO_NOTIFY, "À notifier"),
    (NOTIFICATION_STATUS_NOTIFIED, "Notifié"),
)

ARRETE = "arrete"
LETTRE = "lettre"
LETTRE_REFUS = "refus"

LETTRE_ET_ARRETE_SIGNES = "lettre_et_arrete_signes"
ANNEXE = "annexe"

MIN_DEMANDE_MONTANT_FOR_AVIS_DETR = 100_000

ANNUAIRE_ENTREPRISE_URL = "https://annuaire-entreprises.data.gouv.fr/entreprise/"

# DN

DS_STATE_ACCEPTE = "accepte"
DS_STATE_EN_CONSTRUCTION = "en_construction"
DS_STATE_EN_INSTRUCTION = "en_instruction"
DS_STATE_REFUSE = "refuse"
DS_STATE_SANS_SUITE = "sans_suite"

DS_STATE_VALUES = (
    (DS_STATE_ACCEPTE, "Accepté"),
    (DS_STATE_EN_CONSTRUCTION, "En construction"),
    (DS_STATE_EN_INSTRUCTION, "En instruction"),
    (DS_STATE_REFUSE, "Refusé"),
    (DS_STATE_SANS_SUITE, "Classé sans suite"),
)

# Valeurs de l'enum GraphQL `TraitementEvent` de Démarches Simplifiées
# (https://www.demarches-simplifiees.fr/graphql/schema/enums/TraitementEvent),
DS_TRAITEMENT_EVENT_DEPOSE = "depose"
DS_TRAITEMENT_EVENT_DEPOSE_CORRECTION_USAGER = "depose_correction_usager"
DS_TRAITEMENT_EVENT_DEPOSE_CORRECTION_INSTRUCTEUR = "depose_correction_instructeur"
DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION = "passe_en_instruction"
DS_TRAITEMENT_EVENT_PASSE_EN_INSTRUCTION_AUTOMATIQUEMENT = (
    "passe_en_instruction_automatiquement"
)
DS_TRAITEMENT_EVENT_REPASSE_EN_INSTRUCTION = "repasse_en_instruction"
DS_TRAITEMENT_EVENT_REPASSE_EN_CONSTRUCTION = "repasse_en_construction"
DS_TRAITEMENT_EVENT_ACCEPTE = "accepte"
DS_TRAITEMENT_EVENT_ACCEPTE_AUTOMATIQUEMENT = "accepte_automatiquement"
DS_TRAITEMENT_EVENT_REFUSE = "refuse"
DS_TRAITEMENT_EVENT_REFUSE_AUTOMATIQUEMENT = "refuse_automatiquement"
DS_TRAITEMENT_EVENT_CLASSE_SANS_SUITE = "classe_sans_suite"

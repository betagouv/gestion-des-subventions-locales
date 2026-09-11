# Notes exploration API Fonds Vert

Date : 2026-06-25
API : https://api-fonds-vert.datahub.din.developpement-durable.gouv.fr

## Endpoints disponibles

| Endpoint | Description |
|----------|-------------|
| `POST /fonds_vert/login` | Authentification → Bearer token (JWT) |
| `GET /fonds_vert/v2/dossiers` | Liste paginée de dossiers, nombreux filtres |
| `GET /fonds_vert/v2/dossiers/{dossier_number}` | Détail d'un dossier |
| `GET /fonds_vert/v2/finances/{numero_ej}` | Détail d'un engagement juridique Chorus |
| `GET /fonds_vert/stats/demarches` | Stats agrégées par démarche |
| `GET /fonds_vert/stats/departements` | Stats agrégées par département |
| `GET /fonds_vert/stats/regions` | Stats agrégées par région |
| `GET /fonds_vert/demarches` | Liste des démarches (**bug API** : retourne les données dans `detail[0].input`) |
| `GET /fonds_vert/demarches/{demarche_number}` | Détail d'une démarche |
| `GET /fonds_vert/demarches/metrics_available` | Métriques disponibles par année |

## Paramètres de filtrage (endpoint `/v2/dossiers`)

- `annee_millesime` — année du dossier (2023, 2024, 2025, 2026)
- `state` — statut : `Accepté`, `En instruction`, `En construction`, `Classé sans suite`, `Refusé`
- `siret` — SIRET du bénéficiaire (filtre exact)
- `code_departement` — code INSEE département (ex : `"35"`)
- `code_region` — code INSEE région
- `code_commune` — code INSEE commune
- `demarche_number` — numéro de démarche DS
- `page` + `per_page` — pagination
- `include_finances=true` — ajoute infos Chorus (EJ, paiements)
- `include_metrics=true` — ajoute métriques spécifiques à la démarche

## Réponses aux deux questions initiales

### Q1 : Données de l'année en cours ?

**Oui.** Le millésime 2026 contient **7 354 dossiers** (au 25/06/2026), dont :
- 165 acceptés
- La majorité en instruction ou classés sans suite

Les données sont donc disponibles pour l'année courante, mais la plupart des dossiers ne sont pas encore instruits. Utile pour afficher la liste des demandes en cours par bénéficiaire.

### Q2 : Historique des années précédentes ?

**Oui.** L'API couvre :
- 2023 : 12 838 dossiers
- 2024 : 12 119 dossiers
- 2025 : 10 330 dossiers
- 2026 : 7 354 dossiers (en cours)
- Avant 2023 : pas de données

## Structure d'un dossier (`socle_commun`)

```json
{
  "dossier_number": 12041784,
  "demarche_title": "Prévention des risques d'incendies...",
  "demarche_number": 69279,
  "nom_du_projet": "Réalisation d'un schéma communal DECI",
  "resume_du_projet": "...",
  "entreprise_raison_sociale": "COMMUNE DE MONTJUSTIN",
  "entreprise_forme_juridique": "Commune et commune nouvelle",
  "siret": "21040129500014",
  "code_departement": "04",
  "nom_departement": "Alpes-de-Haute-Provence",
  "code_commune": "04129",
  "nom_commune": "Montjustin",
  "code_postal": "04110",
  "code_region": "93",
  "annee_millesime": 2023,
  "statut": "Accepté",
  "montant_aide_demandee_fond_vert": 3592.0,
  "total_des_depenses": 4490.0,
  "montant_subvention_attribuee": 3592.0,
  "ratio_aide_fonds_vert_sur_total_depenses": 0.8,
  "date_depot": "2023-04-03T12:51:53",
  "date_notification": "2023-08-28",
  "numero_engagement_juridique": "2104133798",
  "demarche_axe": 2,
  "code_chorus_activite": "0380-02-04-01-01",
  "est_prevu_crte": false,
  "population_commune": 57
}
```

**Champs absents / distincts par rapport à DGCL :**
- Pas de `programme` (c'est toujours le programme 380 - Fonds Vert)
- Présence d'un `statut` (les données DGCL sont uniquement les subventions accordées)
- SIRET disponible → SIREN dérivable (9 premiers caractères)
- Beaucoup de métadonnées projet (`resume_du_projet`, `ambition_ecologique_projet`, `population_commune`)

## Démarches disponibles (24 au total)

**Axe 1 — Performance environnementale**
- Biodéchets, Rénovation bâtiment, Éclairage public, Maires bâtisseurs

**Axe 2 — Adaptation au changement climatique**
- Inondations, Incendies, Cyclones, Trait de côte, Montagne, Renaturation, Ingénierie, Plan eau Mayotte

**Axe 3 — Amélioration de la qualité du cadre de vie**
- SN Biodiversité, Agir pour la biodiversité, Covoiturage, Qualité de l'air, Friche, Mobilité rurale, Mobilités durables, Territoire Industrie, Mer et Littoral, Aménagements cyclables, PCAET

## Chevauchement avec données DGCL existantes ?

**Aucun chevauchement.** Le Fonds Vert (programme 380) est distinct des dispositifs DGCL :
- DETR (programme 119)
- DSIL (programme 119)
- DPV (programme 119)
- DSID (programme 122)

Les données Fonds Vert et DGCL peuvent coexister pour un même bénéficiaire (double financement), mais ce sont des subventions différentes sur des programmes budgétaires distincts.

## Liaison avec les données Turgot

Le champ **SIRET** permet de faire la jonction avec les bénéficiaires Turgot :
- `SubventionFondsVert.siret[:9]` = SIREN = `Beneficiaire.siren`
- Possible aussi via `code_departement` + `code_commune` pour les dossiers sans SIRET (rare : 100 % de couverture observée sur l'échantillon testé)

## Proposition d'intégration

### Option retenue : Option A — Nouveau modèle `SubventionFondsVert`

Raisons :
1. Programme budgétaire différent (380 vs 119/122)
2. Champ `statut` absent dans `SubventionDgcl` (les DGCL ne contiennent que les subventions accordées)
3. Clé naturelle différente (basée sur `dossier_number` vs `(exercice, dispositif, beneficiaire, intitule)`)
4. Données SIRET vs SIREN (nécessite conversion)

### Modèle proposé

```python
class SubventionFondsVert(models.Model):
    beneficiaire = models.ForeignKey(Beneficiaire, on_delete=models.CASCADE)
    dossier_number = models.IntegerField(unique=True)
    annee_millesime = models.PositiveSmallIntegerField()
    demarche_title = models.CharField(max_length=200)
    demarche_number = models.IntegerField()
    nom_du_projet = models.TextField()
    statut = models.CharField(max_length=30)  # Accepté, En instruction, ...
    departement = models.ForeignKey("gsl_core.Departement", null=True, ...)
    commune = models.ForeignKey("gsl_core.Commune", null=True, blank=True, ...)
    montant_aide_demandee = models.DecimalField(max_digits=14, decimal_places=2)
    montant_subvention_attribuee = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    total_des_depenses = models.DecimalField(max_digits=14, decimal_places=2)
    date_depot = models.DateTimeField(null=True)
    date_notification = models.DateField(null=True, blank=True)
```

### Tâche Celery + commande de management

- Commande `import_fonds_vert` dans `gsl_suivi_financier/management/commands/`
- Tâche Celery périodique (sync quotidienne ou hebdomadaire)
- Filtrage par `date_derniere_modification__gte` pour les mises à jour incrémentales
- Credentials via variables d'environnement `FONDS_VERT_USERNAME` / `FONDS_VERT_PASSWORD`

### Affichage

Nouvelle section dans `BeneficiaireDetailView` et son template, sous les subventions DGCL.

## Points d'attention

1. **Authentification** : token JWT avec expiration. Prévoir refresh ou re-login à chaque batch.
2. **Pagination** : 42 641 dossiers au total → environ 43 pages à 1 000/page ou 427 pages à 100/page. Une synchronisation complète prend quelques minutes.
3. **Statuts en cours** : pour 2026, la majorité des dossiers sont "en instruction" — l'intérêt est de montrer l'ensemble du pipeline (demandé → accepté), pas seulement les subventions accordées.
4. **Bug API demarches** : l'endpoint `/fonds_vert/demarches` retourne une erreur de validation interne mais les données sont présentes dans `detail[0].input`. Pas bloquant pour l'import des dossiers.
5. **Credentials à ne jamais stocker dans le code** : utiliser des variables d'environnement.

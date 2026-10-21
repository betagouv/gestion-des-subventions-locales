# Proxy DN

Le proxy permet de donner à un partenaire un accès **en lecture seule** à l'API GraphQL de Démarches Numériques, limité à **une démarche** (et éventuellement à **un groupe instructeur**), sans lui filer notre token DN.

Le partenaire tape sur Turgot avec son token proxy, on vérifie ce qu'il demande, on transmet à DN avec notre token, et on filtre la réponse avant de la lui renvoyer.

## Créer un token

Ça se passe dans l'admin, rubrique « Tokens proxy DS » (réservé aux super-users).

1. On crée le token avec un libellé et la démarche autorisée → **la clé s'affiche une seule fois** dans le message de confirmation. On la copie tout de suite, on ne stocke que son empreinte !
2. On rouvre le token pour choisir un groupe instructeur (la liste n'apparaît qu'une fois la démarche enregistrée). Par défaut : « Toute la démarche ».
3. On coche « Actif » : un token est inactif à sa création.

Pour couper un accès, on décoche « Actif ». Pas besoin de supprimer.

## Appeler le proxy

```bash
curl -X POST https://<turgot>/ds-proxy/graphql/ \
  -H "Authorization: Bearer <clé>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "query getDemarche($demarcheNumber: Int!) { demarche(number: $demarcheNumber) { number dossiers { nodes { number groupeInstructeur { id } } } } }",
    "variables": { "demarcheNumber": 12345 }
  }'
```

Même format que l'API DN : `query`, `variables`, `operationName`. Pour écrire ses requêtes, on s'appuie sur la [doc de l'API GraphQL de DN](https://doc.demarche.numerique.gouv.fr/api-graphql) et sur [le schéma](https://www.demarches-simplifiees.fr/graphql/schema/introduction/welcome).

## Ce qui est autorisé (ou pas)

- **Que des queries** : les mutations sont refusées (403).
- À la racine, uniquement `demarche`, `dossier` ou de l'introspection (`__schema`, `__type`, `__typename`). Une seule opération métier par requête, pas d'alias ni de fragment à la racine.
- Pour `demarche`, la variable `demarcheNumber` doit être celle du token.
- Sur le type `Demarche`, seuls certains champs passent (cf. `ALLOWED_DEMARCHE_FIELDS` dans `query_guard.py`). Pas de `groupeInstructeurs { instructeurs }`, par exemple.
- **La requête doit demander `demarche { number }`** (ou `dossier { demarche { number } }`) : c'est sur la réponse de DN qu'on vérifie vraiment le périmètre, pas sur les variables envoyées par l'appelant.
- Si le token est restreint à un groupe instructeur, il faut aussi demander `groupeInstructeur { id }` sur les dossiers. Sinon, ils sont tous filtrés.
- **Une seule requête à la fois par token** : une deuxième requête en parallèle prend une 429.

## Les réponses

- Toutes les erreurs reviennent au format GraphQL, avec un `requestId` dans `extensions`. C'est lui qu'on cherche dans nos logs quand un partenaire remonte un souci.
- Les erreurs détectées avant l'appel à DN (token, requête invalide, champ interdit, 429) ont le bon statut HTTP (401, 400, 403, 429).
- Après, la réponse est streamée : on envoie un espace tout de suite pour passer sous le timeout Scalingo, puis le JSON. Donc **le statut est 200 même si DN a planté ou si la réponse est hors périmètre** : il faut regarder `errors` dans le corps.
- Si DN renvoie une erreur sans données, on la transmet telle quelle (précédée de notre erreur avec le `requestId`).

## Où regarder dans le code

| Fichier | Rôle |
|---|---|
| `views.py` | Point d'entrée `graphql_proxy` : auth, validation, forward vers DN, vérification du périmètre |
| `query_guard.py` | Liste blanche des champs du type `Demarche` |
| `filters.py` | Filtrage des dossiers par groupe instructeur |
| `locks.py` | Verrou Redis « une requête à la fois » par token |
| `models.py` | `ProxyToken` (clé hashée, démarche, groupe instructeur) |

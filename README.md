# Outil de gestion des subventions locales

## Lancement rapide

```bash
source venv/bin/activate
python manage.py runserver
```
Tests :

```bash
python -m pytest
```

Linting :

```bash
ruff format && ruff check --fix
```

## Première installation

Dépendances :
- PostgreSQL ≥ 15
- Python 3.12 (avec pip et venv)

Tout d'abord, créez la base de données en lançant une invite de commande PostgreSQL :

```bash
psql
```

Puis, dans cette invite de commandes, créez la base de données et l'utilisateur : 

```sql
CREATE USER gsl_team WITH PASSWORD 'gsl_pass';
CREATE DATABASE gsl OWNER gsl_team;
ALTER USER gsl_team CREATEDB;
```

Tapez `\q` pour quitter l'invite de commandes PostgreSQL.

Ensuite, il est temps de procéder à l'installation du code et de ses dépendances :

```bash
# Création et activation d’un venv
python -m venv venv
source venv/bin/activate

# Installation des dépendances
pip install -r requirements.txt -r requirements-dev.txt

# Paramétrage
cp .env.example .env

# install pre-commit hooks
pre-commit install

# Initialisation de la base de données
python manage.py migrate

# Création d'un superuser
python manage.py createsuperuser

# Lancement du serveur !
python manage.py runserver
```



## Exécuter Celery

:warning: Tout d'abord, installez et lancez un serveur Redis.

Ensuite, cette commande permet d'exécuter le worker Celery qui exécutera les tâches
planifiées ou cronées :

```bash
python -m celery -A gsl worker --beat --scheduler django -l INFO
```

## Interagir en shell

```bash
python manage.py shell_plus --ipython
```


## Utiliser just

Il est possible d'utiliser [just](https://just.systems/) pour faire tourner l'app.

```shell
just manage COMMAND
```

Les raccourcis suivants existent :
- `just runserver`
- `just shell`
- `just makemigrations`
- `just migrate`

## Configurer le bucket S3 (import/export de documents)

L'import de scans se fait par envoi direct du navigateur vers le bucket S3 (POST
présigné, voir `gsl_notification.views.import_views`). Pour que le navigateur soit
autorisé à uploader, le bucket doit porter une règle CORS autorisant les requêtes
`POST` depuis l'origine de l'app. Sans cette règle, S3/Scaleway répond `403` sans
en-tête `Access-Control-Allow-Origin` et le navigateur signale une erreur
cross-origin.

La commande configure aussi des règles de cycle de vie qui font expirer après
1 jour les objets temporaires d'import et d'export.

```bash
# Définir la règle CORS pour une ou plusieurs origines
python manage.py configure_s3_bucket --origin http://localhost:8000
python manage.py configure_s3_bucket --origin https://turgot.example.gouv.fr

# Afficher la configuration CORS et de cycle de vie actuelle du bucket
python manage.py configure_s3_bucket --show
```

L'option `--origin` peut être répétée pour autoriser plusieurs origines. La
variable d'environnement `AWS_STORAGE_BUCKET_NAME` doit être configurée.

## Déploiement en production

Le déploiement en production est automatisé via GitHub Actions.

### Procédure

1. Se placer sur le commit à déployer (pas nécessairement le dernier commit de `main` — on peut remonter de quelques commits pour exclure des changements pas encore testés)

   > Le commit doit appartenir à la branche `main` ou à une branche `hotfix/*`.
   > GitHub n'exécute les tests automatiquement (hors PR) que sur ces branches
   > (voir `.github/workflows/django.yml`), et le déploiement par tag exige des
   > tests valides. Une branche `hotfix/*` sert typiquement à isoler un correctif
   > urgent par cherry-pick : on crée la branche depuis le tag de la dernière
   > release déployée, on y cherry-pick uniquement le ou les commits du fix, puis
   > on tagge ce commit — ce qui permet de déployer sans embarquer les commits
   > de `main` postérieurs à cette release qui n'auraient pas encore été recettés.

2. Lancer la commande :

```bash
just release
```

Cette commande crée automatiquement un tag au format `vYY.MM.DD` (avec un suffixe incrémental si un tag existe déjà pour la date) et le pousse sur le dépôt distant.

3. Le workflow GitHub Actions se déclenche automatiquement et :
   - exécute les tests
   - crée une **Release GitHub** avec les notes auto-générées (liste des PRs depuis le dernier tag)
   - déploie sur Scalingo via l'API Sources

   > Les notes auto-générées par GitHub se basent sur les PRs mergées dans la
   > branche par défaut (`main`) depuis le dernier tag. Elles sont fiables pour
   > un tag posé sur `main`. En revanche, pour un tag posé depuis une branche
   > `hotfix/*`, les notes auto-générées ne reflètent pas le contenu réel du
   > hotfix (elles listent les PRs de `main` postérieures à la release
   > précédente) : il faut alors les réécrire à la main une fois la Release
   > créée.

4. **Confirmer le déploiement côté GitHub** : le job `deploy` utilise l'environnement `production`, qui nécessite une approbation manuelle dans GitHub. Un reviewer autorisé doit approuver le déploiement depuis l'interface GitHub Actions avant que celui-ci ne s'exécute.

### Prérequis

- Le secret `SCALINGO_API_TOKEN` doit être configuré dans l'environnement GitHub `production`
- L'environnement `production` doit avoir les règles de protection (reviewers requis) configurées dans **Settings > Environments** du dépôt GitHub

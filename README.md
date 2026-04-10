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

## Déploiement en production

Le déploiement en production est automatisé via GitHub Actions.

### Procédure

1. Se placer sur le commit à déployer (pas nécessairement le dernier commit de `main` — on peut remonter de quelques commits pour exclure des changements pas encore testés)
2. Lancer la commande :

```bash
just release
```

Cette commande crée automatiquement un tag au format `vYY.MM.DD` (avec un suffixe incrémental si un tag existe déjà pour la date) et le pousse sur le dépôt distant.

3. Le workflow GitHub Actions se déclenche automatiquement et :
   - exécute les tests
   - crée une **Release GitHub** avec les notes auto-générées (liste des PRs depuis le dernier tag)
   - déploie sur Scalingo via l'API Sources

4. **Confirmer le déploiement côté GitHub** : le job `deploy` utilise l'environnement `production`, qui nécessite une approbation manuelle dans GitHub. Un reviewer autorisé doit approuver le déploiement depuis l'interface GitHub Actions avant que celui-ci ne s'exécute.

### Prérequis

- Le secret `SCALINGO_API_TOKEN` doit être configuré dans l'environnement GitHub `production`
- L'environnement `production` doit avoir les règles de protection (reviewers requis) configurées dans **Settings > Environments** du dépôt GitHub

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

### Dépendances :
- Python 3.12 (avec pip et venv)
- Docker & Docker compose

Tout d'abord, démarrez PostgreSQL via Docker :

```bash
docker compose up -d
```
> PostgreSQL sera automatiquement initialisé avec le script [init.sql](./docker/postgresql/init.sql)



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

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
- PostgreSQL
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

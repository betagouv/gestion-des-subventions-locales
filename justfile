set dotenv-load

default:
    just --list

# Install Javascript dependencies
install-js:
    npm install
    # For JS deps that distribute a bundle, just vendorize it
    while read jsfile; do cp "node_modules/$jsfile" "static/vendor/"; echo "Vendorized $jsfile"; done <vendorize.txt

manage command:
    DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py {{command}}


# Django shorthands
runserver: (manage "runserver")
migrate: (manage "migrate")
shell: (manage "shell")
makemigrations: (manage "makemigrations")
    ruff format */migrations/*.py

test:
    pytest

# Watch the repo and launch pytest on files save
test-watching folder_or_file:
    git ls-files | entr -c pytest -vv {{folder_or_file}}


# Scalingo: SSH
scalingo-django-ssh environment:
    scalingo run --app gsl-{{environment}} bash

# Scalingo: run Django command
scalingo-django-command environment command:
    scalingo run --app gsl-{{environment}} {{ if environment == "prod" { "--region osc-secnum-fr1" } else { "" } }} python manage.py {{command}}

# Scalingo: login to Django shell
scalingo-django-shell environment: (scalingo-django-command environment "shell")

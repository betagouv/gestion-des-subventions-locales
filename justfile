set dotenv-load

default:
    just --list

# Install Javascript dependencies
install-js:
    npm ci --ignore-scripts
    # For JS deps that distribute a bundle, just vendorize it
    while read jsfile; do cp "node_modules/$jsfile" "static/vendor/"; echo "Vendorized $jsfile"; done <vendorize.txt
    npm run build # to build tiptap bundle

run-celery:
    python -m celery --app gsl worker --beat --loglevel INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

manage command:
    python manage.py {{command}}


# Django shorthands
runserver: (manage "runserver")
migrate: (manage "migrate")
shell: (manage "shell")
makemigrations: (manage "makemigrations")
    ruff format */migrations/*.py

migr app migration_number:
    python manage.py migrate {{app}} {{migration_number}}

test:
    pytest

# Watch the repo and launch pytest on files save
test-watching folder_or_file:
    git ls-files | entr -c pytest -vv {{folder_or_file}}


# Create a release tag (vYY.MM.DD) and push it to trigger production deployment
release:
    #!/usr/bin/env bash
    set -euo pipefail
    git fetch --tags
    BASE_TAG="v$(date +%y.%m.%d)"
    if ! git tag --list | grep -qx "$BASE_TAG"; then
        TAG="$BASE_TAG"
    else
        LAST=$(git tag --list "${BASE_TAG}.*" | sed "s/${BASE_TAG}\.//" | sort -n | tail -1)
        TAG="${BASE_TAG}.$((${LAST:-0} + 1))"
    fi
    echo "Creating and pushing tag: $TAG"
    git tag "$TAG"
    git push origin "$TAG"

# Scalingo: SSH
scalingo-django-ssh environment:
    scalingo run --app gsl-{{environment}} bash

# Scalingo: run Django command
scalingo-django-command environment command:
    scalingo run --app gsl-{{environment}} {{ if environment == "prod" { "--region osc-secnum-fr1" } else { "" } }} python manage.py {{command}}

# Scalingo: login to Django shell
scalingo-django-shell environment: (scalingo-django-command environment "shell")

# Scalingo: copy a database of a review app from parent
scalingo-load-review-app environment pr_number:
    scalingo run --app gsl-{{environment}}-pr{{ pr_number }} "bash bin/copy_db.sh && python manage.py migrate"

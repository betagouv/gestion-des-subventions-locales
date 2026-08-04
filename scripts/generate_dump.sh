#!/bin/bash

if [ -f .env ]; then
  set -a
  source ./.env
  set +a
fi

if [ -z "$1" ]; then
  echo "Utilisation : $0 <plateforme>"
  echo "Plateformes disponibles : local, staging, prod"
  exit 1
fi

PLATFORM=$1
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# Binary .dump for Scalingo (pg_dump -F c), .sql for local (SQL txt)
if [[ "$PLATFORM" == "local" ]]; then EXT="sql"; else EXT="dump"; fi
DUMP_FILE="./tmp/db_dump_${PLATFORM}_${TIMESTAMP}.${EXT}"
mkdir -p "$(dirname "$DUMP_FILE")"

if [[ "$PLATFORM" == "local" ]]; then
  echo "Génération du dump de la base de données locale..."

  REQUIRED_VARS=("DATABASE_NAME" "DATABASE_USER" "DATABASE_PASSWORD" "DATABASE_HOST" "DATABASE_PORT")
  for VAR in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!VAR}" ]]; then
      echo "Erreur : $VAR n'est pas définie dans l'environnement."
      exit 1
    fi
  done

  # Local
  if pg_dump -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" -f "$DUMP_FILE"; then
    echo "Dump de la base de données locale enregistré dans : $DUMP_FILE"
  else
    echo "Erreur : le dump de la base locale a échoué."
    exit 1
  fi

elif [[ "$PLATFORM" == "staging" || "$PLATFORM" == "prod" ]]; then
  echo "Génération du dump de la base de données depuis Scalingo ($PLATFORM)..."

  if ! command -v scalingo &> /dev/null; then
    echo "Erreur : l'outil CLI Scalingo n'est pas installé. Installez-le depuis https://doc.scalingo.com/cli/install"
    exit 1
  fi

  if [[ "$PLATFORM" == "staging" ]]; then
    SCALINGO_APP="gsl-staging"
    REGION="osc-fr1"
  else
    SCALINGO_APP="gsl-prod"
    REGION="osc-secnum-fr1"
  fi

  SCALINGO_DB_URL=$(scalingo --app "$SCALINGO_APP" --region="$REGION" env-get SCALINGO_POSTGRESQL_URL)
  
  if [ -z "$SCALINGO_DB_URL" ]; then
    echo "Erreur : impossible de récupérer l'URL de la base de données depuis Scalingo."
    exit 1
  fi

  USER=$(echo "$SCALINGO_DB_URL" | sed -E 's|postgres://([^:]+):.*|\1|')
  PASSWORD=$(echo "$SCALINGO_DB_URL" | sed -E 's|postgres://[^:]+:([^@]+).*|\1|')
  NAME=$(echo "$SCALINGO_DB_URL" | sed -E 's|postgres://[^:]+:[^@]+@[^:]+:[^/]+/(.*)|\1|')

  echo "Connexion à la base de données Scalingo..."
  
  TUNNEL_LOG=$(mktemp)
  scalingo --app "$SCALINGO_APP" --region "$REGION" db-tunnel "$SCALINGO_DB_URL" >"$TUNNEL_LOG" 2>&1 &

  # db-tunnel PID
  TUNNEL_PID=$!
  # Let's close the tunnel when it's done
  trap 'echo "Fermeture du tunnel."; kill "$TUNNEL_PID" 2>/dev/null; wait "$TUNNEL_PID" 2>/dev/null; rm -f "$TUNNEL_LOG"' EXIT

  sleep 5

  TUNNEL_OUTPUT=$(ps aux | grep "$TUNNEL_PID" | grep -v "grep")

  if [ -z "$TUNNEL_OUTPUT" ]; then
    echo "Erreur : le tunnel n'a pas pu être établi ou n'est pas actif."
    cat "$TUNNEL_LOG" >&2
    exit 1
  else
    echo "Tunnel actif, poursuite de l'opération..."
  fi

  PORT=$(lsof -i -n -P | grep "127.0.0.1" | grep -o '[0-9]\{2,5\}' | tail -n 1)

  if [ -z "$PORT" ]; then
    echo "Erreur : impossible de récupérer le port."
    exit 1
  fi
  DB_URL="postgres://$USER:$PASSWORD@127.0.0.1:$PORT/$NAME"

  echo "Dump en cours..."

  if pg_dump "$DB_URL" -F c -f "$DUMP_FILE"; then
    echo "Dump de la base de données Scalingo enregistré dans : $DUMP_FILE"
  else
    echo "Erreur : le dump Scalingo a échoué."
    exit 1
  fi

else
  echo "Erreur : plateforme invalide. Utilisez 'local', 'staging' ou 'prod'."
  exit 1
fi

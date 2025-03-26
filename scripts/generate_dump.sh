#!/bin/bash

# Charge des variables d'environnement depuis le fichier .env si présent
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Vérifie les paramètres requis
if [ -z "$1" ]; then
  echo "Utilisation : $0 <plateforme>"
  echo "Plateformes disponibles : local, staging, prod"
  exit 1
fi

VERBOSE=false
# Analyse les arguments
for arg in "$@"; do
  if [ "$arg" == "--verbose" ]; then
    VERBOSE=true
  fi
done

PLATFORM=$1
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DUMP_FILE="./tmp/db_dump_${PLATFORM}_${TIMESTAMP}.sql"

if [[ "$PLATFORM" == "local" ]]; then
  echo "Génération du dump de la base de données locale..."

  # Vérifie que les variables d'environnement requises sont définies
  REQUIRED_VARS=("DATABASE_NAME" "DATABASE_USER" "DATABASE_PASSWORD" "DATABASE_HOST" "DATABASE_PORT")
  for VAR in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!VAR}" ]]; then
      echo "Erreur : $VAR n'est pas définie dans l'environnement."
      exit 1
    fi
  done

  # Générer le dump depuis la base locale
  pg_dump -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" -f "$DUMP_FILE"
  echo "Dump de la base de données locale enregistré dans : $DUMP_FILE"

elif [[ "$PLATFORM" == "staging" || "$PLATFORM" == "prod" ]]; then
  echo "Génération du dump de la base de données depuis Scalingo ($PLATFORM)..."

  # Vérifie que l'outil CLI Scalingo est installé
  if ! command -v scalingo &> /dev/null; then
    echo "Erreur : l'outil CLI Scalingo n'est pas installé. Installez-le depuis https://doc.scalingo.com/cli/install"
    exit 1
  fi

  # Définit le nom de l'application Scalingo (modifiez si nécessaire)
  if [[ "$PLATFORM" == "staging" ]]; then
    SCALINGO_APP="gsl-staging"
    REGION="osc-fr1"
  else
    SCALINGO_APP="gsl-prod"
    REGION="osc-secnum-fr1"
  fi

  # Récupère l'URL de la base de données depuis Scalingo
  SCALINGO_DB_URL=$(scalingo --app "$SCALINGO_APP" --region="$REGION" env-get SCALINGO_POSTGRESQL_URL)
  
  if [ -z "$SCALINGO_DB_URL" ]; then
    echo "Erreur : impossible de récupérer l'URL de la base de données depuis Scalingo."
    exit 1
  fi

  USER=$(echo "$SCALINGO_DB_URL" | sed -E 's|postgres://([^:]+):.*|\1|')
  PASSWORD=$(echo "$SCALINGO_DB_URL" | sed -E 's|postgres://[^:]+:([^@]+).*|\1|')
  NAME=$(echo "$SCALINGO_DB_URL" | sed -E 's|postgres://[^:]+:[^@]+@[^:]+:[^/]+/(.*)|\1|')

  echo "Connexion à la base de données Scalingo..."
  
  # Exécute le tunnel db-tunnel en arrière-plan et capturer la sortie
  scalingo --app "$SCALINGO_APP" --region "$REGION" db-tunnel "$SCALINGO_DB_URL" &
  
  # Capture le PID du processus db-tunnel
  TUNNEL_PID=$!

  sleep 5

  TUNNEL_OUTPUT=$(ps aux | grep "$TUNNEL_PID" | grep -v "grep")

  # Si le tunnel est actif, on continue, sinon on arrête le script
  if [ -z "$TUNNEL_OUTPUT" ]; then
    echo "Erreur : le tunnel n'a pas pu être établi ou n'est pas actif."
    exit 1
  else
    echo "Tunnel actif, poursuite de l'opération..."
  fi

  # Extraction du port local utilisé par le tunnel
  PORT=$(lsof -i -n -P | grep "127.0.0.1" | grep -o '[0-9]\{2,5\}' | tail -n 1)

  # Vérifie du port
  if [ -z "$PORT" ]; then
    echo "Erreur : impossible de récupérer le port."
    exit 1
  fi
  DB_URL="postgres://$USER:$PASSWORD@127.0.0.1:$PORT/$NAME"

  echo "Dump en cours..."

  # Génère le dump depuis Scalingo
  pg_dump "$DB_URL" -F c -f "$DUMP_FILE"
  
  echo "Dump de la base de données Scalingo enregistré dans : $DUMP_FILE"

else
  echo "Erreur : plateforme invalide. Utilisez 'local', 'staging' ou 'prod'."
  exit 1
fi
#!/bin/bash

# Charge les variables d'environnement depuis le fichier .env si présent
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi
echo "DATABASE_PORT=$DATABASE_PORT"

# Vérifie si les variables d'environnement requises sont définies
VARIABLES_REQUISES=("DATABASE_NAME" "DATABASE_USER" "DATABASE_PASSWORD" "DATABASE_HOST" "DATABASE_PORT" "DATABASE_URL")
for VAR in "${VARIABLES_REQUISES[@]}"; do
  if [[ -z "${!VAR}" ]]; then
    echo "Erreur : $VAR n'est pas définie dans l'environnement."
    exit 1
  fi
done

KILL_THEN_CREATE_A_DB=false
VERBOSE=false

# Analyse les arguments
for arg in "$@"; do
  if [ "$arg" == "--new-db" ]; then
    KILL_THEN_CREATE_A_DB=true
  elif [ "$arg" == "--verbose" ]; then
    VERBOSE=true
  fi
done

# Vérifie les connexions actives sur la base
CONNEXIONS_ACTIVES=$(PGPASSWORD=$DATABASE_PASSWORD psql -h "$DATABASE_HOST" -U "$DATABASE_USER" -d postgres -t -c "
SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$DATABASE_NAME';" | xargs)

if [ "$CONNEXIONS_ACTIVES" -gt 0 ]; then
  echo "⚠️  La base de données '$DATABASE_NAME' a $CONNEXIONS_ACTIVES connexion(s) active(s)."
  read -p "Voulez-vous forcer la fermeture de ces connexions ? (o/n) " REPONSE
  case "$REPONSE" in
    [oO][uU][iI]|[oO]|[yY]|[yY][eE][sS])
      echo "🔨 Fermeture des connexions en cours..."
      PGPASSWORD=$DATABASE_PASSWORD psql -h "$DATABASE_HOST" -U "$DATABASE_USER" -d postgres -c "
      SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DATABASE_NAME' AND pid <> pg_backend_pid();"
      ;;
    *)
      echo "🚫 Opération annulée. La base est toujours utilisée."
      exit 1
      ;;
  esac
else
  echo "✅ Aucune connexion active trouvée sur '$DATABASE_NAME'."
fi

# Liste les fichiers de dump dans /tmp et permettre à l'utilisateur d'en sélectionner un
FICHIERS_DUMP=(./tmp/*.sql)
if [ ${#FICHIERS_DUMP[@]} -eq 0 ]; then
  echo "Aucun fichier de dump SQL trouvé dans /tmp."
  exit 1
elif [ ${#FICHIERS_DUMP[@]} -eq 1 ]; then
  FICHIER_DUMP="${FICHIERS_DUMP[0]}"
else
  echo "Plusieurs fichiers de dump trouvés dans /tmp. Sélectionnez-en un :"
  select FICHIER_DUMP in "${FICHIERS_DUMP[@]}"; do
    if [ -n "$FICHIER_DUMP" ]; then
      break
    else
      echo "Sélection invalide."
    fi
  done
fi

# Supprime la base de données si le flag --new-db est défini
if [ "$KILL_THEN_CREATE_A_DB" = true ]; then
  echo "Suppression de la base de données $DATABASE_NAME..."
  dropdb -h "$DATABASE_HOST" -U "$DATABASE_USER" "$DATABASE_NAME"
  
  echo "Création de la base de données $DATABASE_NAME..."
  createdb -h "$DATABASE_HOST" -U "$DATABASE_USER" "$DATABASE_NAME"
else
  if command -v python &> /dev/null; then
    python manage.py flush --noinput
  else
    echo "Python ou manage.py introuvable. Assurez-vous que les migrations sont appliquées manuellement."
  fi
fi

# Restaure la base de données
echo "Restauration de la base de données depuis $FICHIER_DUMP..."
if [ "$VERBOSE" = true ]; then
  pg_restore -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" --verbose "$FICHIER_DUMP"
else
  pg_restore -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" "$FICHIER_DUMP"
fi

# Exécute les migrations
echo "Vérification des migrations en attente..."
if command -v python &> /dev/null; then
  python manage.py migrate
else
  echo "Python ou manage.py introuvable. Assurez-vous que les migrations sont appliquées manuellement."
fi

echo "Restauration de la base de données terminée."
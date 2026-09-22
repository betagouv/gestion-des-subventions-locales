#!/bin/bash
#
# Usage : ./scripts/restore_db.sh [--new-db] [--verbose] [chemin/vers/dump]
#
# Restaure la base de données à partir d'un dump Postgres. Le format est
# détecté automatiquement (texte via psql, ou custom/tar via pg_restore).
# Si aucun chemin n'est donné, le script cherche dans ./tmp/*.sql, *.dump et
# *.backup (s'il y en a plusieurs, un choix est proposé).
#   --new-db   Supprime puis recrée la base au lieu de la vider (flush).
#   --verbose  Affiche le détail de la restauration.
#
# Variables d'environnement requises (chargées depuis .env si présent) :
#   DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD, DATABASE_HOST,
#   DATABASE_PORT, DATABASE_URL
#
# Nécessite psql/pg_restore/dropdb/createdb, et uv (pour les commandes
# `manage.py`, sinon les migrations doivent être appliquées manuellement).

# Charge les variables d'environnement depuis le fichier .env si présent.
# `source` (plutôt que `export $(... | xargs)`) est nécessaire pour que les
# références du type ${DATABASE_USER} dans DATABASE_URL soient expansées.
if [ -f .env ]; then
  set -a
  source .env
  set +a
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
FICHIER_DUMP_ARG=""

# Analyse les arguments
for arg in "$@"; do
  if [ "$arg" == "--new-db" ]; then
    KILL_THEN_CREATE_A_DB=true
  elif [ "$arg" == "--verbose" ]; then
    VERBOSE=true
  else
    FICHIER_DUMP_ARG="$arg"
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

# Détermine le fichier de dump : celui passé en argument, ou une sélection
# parmi les fichiers trouvés dans ./tmp.
if [ -n "$FICHIER_DUMP_ARG" ]; then
  if [ ! -f "$FICHIER_DUMP_ARG" ]; then
    echo "Fichier de dump introuvable : $FICHIER_DUMP_ARG"
    exit 1
  fi
  FICHIER_DUMP="$FICHIER_DUMP_ARG"
else
  shopt -s nullglob
  FICHIERS_DUMP=(./tmp/*.sql ./tmp/*.dump ./tmp/*.backup)
  shopt -u nullglob
  if [ ${#FICHIERS_DUMP[@]} -eq 0 ]; then
    echo "Aucun fichier de dump trouvé dans ./tmp."
    exit 1
  elif [ ${#FICHIERS_DUMP[@]} -eq 1 ]; then
    FICHIER_DUMP="${FICHIERS_DUMP[0]}"
  else
    echo "Plusieurs fichiers de dump trouvés dans ./tmp. Sélectionnez-en un :"
    select FICHIER_DUMP in "${FICHIERS_DUMP[@]}"; do
      if [ -n "$FICHIER_DUMP" ]; then
        break
      else
        echo "Sélection invalide."
      fi
    done
  fi
fi

# Supprime la base de données si le flag --new-db est défini
if [ "$KILL_THEN_CREATE_A_DB" = true ]; then
  echo "Suppression de la base de données $DATABASE_NAME..."
  dropdb -h "$DATABASE_HOST" -U "$DATABASE_USER" "$DATABASE_NAME"
  
  echo "Création de la base de données $DATABASE_NAME..."
  createdb -h "$DATABASE_HOST" -U "$DATABASE_USER" "$DATABASE_NAME"
else
  if command -v uv &> /dev/null; then
    uv run python manage.py flush --noinput
  else
    echo "uv introuvable. Assurez-vous que les migrations sont appliquées manuellement."
  fi
fi

# Restaure la base de données. Un dump custom/tar (pg_dump -Fc/-Ft, souvent
# en .dump ou .backup) commence par la signature "PGDMP" et doit passer par
# pg_restore ; un dump texte (pg_dump -Fp, souvent en .sql) doit passer par
# psql.
echo "Restauration de la base de données depuis $FICHIER_DUMP..."
if [ "$(head -c 5 "$FICHIER_DUMP")" = "PGDMP" ]; then
  if [ "$VERBOSE" = true ]; then
    pg_restore -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" --verbose "$FICHIER_DUMP"
  else
    pg_restore -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" "$FICHIER_DUMP"
  fi
else
  if [ "$VERBOSE" = true ]; then
    PGPASSWORD=$DATABASE_PASSWORD psql -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" -f "$FICHIER_DUMP"
  else
    PGPASSWORD=$DATABASE_PASSWORD psql -h "$DATABASE_HOST" -U "$DATABASE_USER" -d "$DATABASE_NAME" -q -f "$FICHIER_DUMP"
  fi
fi

# Exécute les migrations
echo "Vérification des migrations en attente..."
if command -v uv &> /dev/null; then
  uv run python manage.py migrate
else
  echo "uv introuvable. Assurez-vous que les migrations sont appliquées manuellement."
fi

echo "Restauration de la base de données terminée."
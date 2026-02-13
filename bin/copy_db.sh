#!/bin/bash

# This script copy DB from parent app in review apps

if [[ "$APP" == "gsl-prod" || "$APP" == "gsl-staging" || "$APP" == "gsl-demo" ]]; then
  exit 0
fi

SRC_DB_URL="$PARENT_DATABASE_URL"
DEST_DB_URL="$SCALINGO_POSTGRESQL_URL"

if [[ "$SRC_DB_URL" == "$DEST_DB_URL" ]]; then
  echo "SRC_DB_URL and DEST_DB_URL are identical. Aborting."
  exit 0
fi

dbclient-fetcher psql 16
pg_dump \
  --clean \
  --if-exists \
  --format c \
  --dbname "$SRC_DB_URL" \
  --no-owner \
  --no-privileges \
  --no-comments \
  --exclude-schema 'information_schema' \
  --exclude-schema '^pg_*' \
  --file dump.pgsql

# Drop all tables in the target database
psql $DEST_DB_URL -c "
DO \$\$
DECLARE
    r RECORD;
BEGIN
    RAISE NOTICE 'Starting to drop tables';
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        BEGIN
            RAISE NOTICE 'Dropping table: %', r.tablename;
            EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Error dropping table: %', r.tablename;
        END;
    END LOOP;
    RAISE NOTICE 'Finished dropping tables';
END
\$\$;"


echo "Importing dump.pgsql..."

pg_restore --no-owner --no-privileges --no-comments --dbname $DEST_DB_URL dump.pgsql

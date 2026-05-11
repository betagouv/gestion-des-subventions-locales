from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class PostgresOnlyRunSQL(migrations.RunSQL):
    """RunSQL variant that no-ops on non-PostgreSQL backends (e.g. test SQLite)."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != "postgresql":
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_demarches_simplifiees", "0056_merge_20260427_1223"),
    ]

    operations = [
        UnaccentExtension(),
        TrigramExtension(),
        PostgresOnlyRunSQL(
            sql=(
                "CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text "
                "AS $$ SELECT public.unaccent('public.unaccent', $1) $$ "
                "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;"
            ),
            reverse_sql="DROP FUNCTION IF EXISTS f_unaccent(text);",
        ),
        PostgresOnlyRunSQL(
            sql=(
                "CREATE INDEX dossier_intitule_trgm_idx "
                "ON gsl_demarches_simplifiees_dossier "
                "USING gin (f_unaccent(projet_intitule) gin_trgm_ops);"
            ),
            reverse_sql="DROP INDEX IF EXISTS dossier_intitule_trgm_idx;",
        ),
        PostgresOnlyRunSQL(
            sql=(
                "CREATE INDEX personnemorale_rs_trgm_idx "
                "ON gsl_demarches_simplifiees_personnemorale "
                "USING gin (f_unaccent(raison_sociale) gin_trgm_ops);"
            ),
            reverse_sql="DROP INDEX IF EXISTS personnemorale_rs_trgm_idx;",
        ),
    ]

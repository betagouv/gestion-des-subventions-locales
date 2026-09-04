import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from gsl.stats.models import FondsVertImportState
from gsl.stats.tasks import (
    FONDS_VERT_BASE_URL,
    _fonds_vert_login,
    _iter_fonds_vert_pages,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_fonds_vert [--restart]
    (credentials lus depuis FONDS_VERT_USERNAME / FONDS_VERT_PASSWORD via settings.py)

    Reprend automatiquement après la dernière page importée avec succès (curseur
    partagé avec la tâche Celery `fetch_subventions_fonds_vert`). Utiliser --restart
    pour forcer une reprise depuis la page 1.
    """

    help = "Importe les subventions Fonds Vert depuis l'API datahub"

    def add_arguments(self, parser):
        parser.add_argument(
            "--restart",
            action="store_true",
            help="Ignore le curseur de reprise et repart de la page 1.",
        )

    def handle(self, *args, restart, **kwargs):
        username = settings.FONDS_VERT_USERNAME
        password = settings.FONDS_VERT_PASSWORD
        if not username or not password:
            self.stderr.write(
                self.style.ERROR(
                    "Variables FONDS_VERT_USERNAME et FONDS_VERT_PASSWORD requises (voir .env.example)"
                )
            )
            return

        self.stdout.write(f"Authentification sur {FONDS_VERT_BASE_URL}…")
        token = _fonds_vert_login(username, password)
        self.stdout.write("Token obtenu.")

        state = FondsVertImportState.load()
        start_page = 1 if restart else state.last_page + 1
        if start_page > 1:
            self.stdout.write(f"Reprise à la page {start_page}.")

        nb_created = nb_updated = nb_errors = 0

        for page, created, updated, errors in _iter_fonds_vert_pages(
            token, start_page=start_page
        ):
            nb_created += created
            nb_updated += updated
            nb_errors += len(errors)
            self.stdout.write(f"Page {page} — {created} créés, {updated} mis à jour…")
            for err in errors:
                self.stderr.write(
                    self.style.ERROR(
                        f"  Erreur dossier #{err['dossier_number']}: {err['error']}"
                    )
                )
            state.last_page = page
            state.save(update_fields=["last_page", "updated_at"])

        # Synchronisation complète : on repartira de la page 1 au prochain lancement.
        state.last_page = 0
        state.save(update_fields=["last_page", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Import terminé : {nb_created} créés, {nb_updated} mis à jour, {nb_errors} erreurs"
            )
        )

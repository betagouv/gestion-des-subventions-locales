import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from gsl_suivi_financier.tasks import (
    FONDS_VERT_BASE_URL,
    _fonds_vert_get,
    _fonds_vert_login,
    _import_fonds_vert_dossier,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    python manage.py import_subventions_fonds_vert
    (credentials lus depuis FONDS_VERT_USERNAME / FONDS_VERT_PASSWORD via settings.py)
    """

    help = "Importe les subventions Fonds Vert depuis l'API datahub"

    def handle(self, *args, **kwargs):
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

        nb_created = nb_updated = nb_errors = 0
        page = 1
        per_page = 500

        while True:
            data = _fonds_vert_get(
                token, "/fonds_vert/v2/dossiers", page=page, per_page=per_page
            )
            items = data.get("data", [])
            if not items:
                break

            total = data.get("count", "?")
            self.stdout.write(f"Page {page} — {len(items)} dossiers (total : {total})…")

            for item in items:
                try:
                    created = _import_fonds_vert_dossier(item)
                except Exception as e:
                    sc = item.get("socle_commun", {})
                    self.stderr.write(
                        self.style.ERROR(
                            f"  Erreur dossier #{sc.get('dossier_number')}: {e}"
                        )
                    )
                    nb_errors += 1
                    continue
                if created:
                    nb_created += 1
                else:
                    nb_updated += 1

            if data.get("next_page") is None:
                break
            page += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import terminé : {nb_created} créés, {nb_updated} mis à jour, {nb_errors} erreurs"
            )
        )

import requests
from django.conf import settings

FONDS_VERT_BASE_URL = "https://api-fonds-vert.datahub.din.developpement-durable.gouv.fr"


class FondsVertCredentialsMissing(Exception):
    """Levée par `FondsVertClient` quand `settings.FONDS_VERT_USERNAME` /
    `FONDS_VERT_PASSWORD` ne sont pas configurés."""


class FondsVertClient:
    """Client pour l'API Fonds Vert : s'authentifie à l'instanciation
    (identifiants lus depuis `settings.FONDS_VERT_USERNAME` /
    `FONDS_VERT_PASSWORD`) et conserve le token pour les appels suivants."""

    def __init__(self):
        self.token = self._login()

    def _login(self) -> str:
        if not settings.FONDS_VERT_USERNAME or not settings.FONDS_VERT_PASSWORD:
            raise FondsVertCredentialsMissing(
                "Variables FONDS_VERT_USERNAME et FONDS_VERT_PASSWORD requises "
                "(voir .env.example)"
            )
        resp = requests.post(
            f"{FONDS_VERT_BASE_URL}/fonds_vert/login",
            headers={"Accept": "application/json"},
            data={
                "username": settings.FONDS_VERT_USERNAME,
                "password": settings.FONDS_VERT_PASSWORD,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def get(self, path: str, **params) -> dict:
        resp = requests.get(
            f"{FONDS_VERT_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def iter_dossiers_pages(
        self,
        start_page: int = 1,
        per_page: int = 500,
        since: str | None = None,
    ):
        """Parcourt `/fonds_vert/v2/dossiers` à partir de `start_page`. Cède
        `(page, items)` pour chaque page non vide, jusqu'à ce que l'API
        n'indique plus de `next_page`. Ne fait qu'appeler l'API : le
        traitement des `items` (import en base) est à la charge de
        l'appelant.

        `date_derniere_modification__gte` restreint aux dossiers modifiés
        depuis cette date (omis si `None`, pour un import complet) ; transmis
        tel quel à l'API, au format qu'elle attend."""
        params = {"per_page": per_page}
        if since:
            params["date_derniere_modification__gte"] = since

        page = start_page
        while True:
            data = self.get("/fonds_vert/v2/dossiers", page=page, **params)
            items = data.get("data", [])
            if not items:
                return

            yield page, items

            if data.get("next_page") is None:
                return
            page += 1

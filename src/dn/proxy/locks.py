import logging

import redis
from django.conf import settings

from dn.proxy.exceptions import ProxyError

logger = logging.getLogger(__name__)


def acquire_token_lock(token_id):
    """Verrou Redis non bloquant : une requête proxy en vol par token.

    Retourne l'objet lock si acquis, lève ProxyError (429) s'il est déjà
    détenu (une autre requête du même token tourne déjà).
    """
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    lock = client.lock(
        f"ds-proxy:token:{token_id}",
        timeout=settings.DS_PROXY_TOKEN_LOCK_TIMEOUT,
    )
    if not lock.acquire(blocking=False):
        raise ProxyError(
            "Une seule requête à la fois est autorisée par token. "
            "Une requête est déjà en cours pour ce token, attendez sa fin "
            "avant d'en envoyer une autre.",
            429,
        )
    return lock


def release_token_lock(lock, token_id):
    try:
        lock.release()
    except redis.exceptions.LockError:
        # TTL expiré avant la fin du forward : le verrou ne nous appartient
        # plus. On laisse passer (try étroit, type ciblé).
        logger.warning(
            "DS proxy token lock for token %s expired before release "
            "(request longer than DS_PROXY_TOKEN_LOCK_TIMEOUT?)",
            token_id,
        )

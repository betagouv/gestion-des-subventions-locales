import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def acquire_token_lock(token_id):
    """Verrou Redis non bloquant : une requête proxy en vol par token.

    Retourne l'objet lock si acquis, None s'il est déjà détenu (une autre
    requête du même token tourne déjà).
    """
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    lock = client.lock(
        f"ds-proxy:token:{token_id}",
        timeout=settings.DS_PROXY_TOKEN_LOCK_TIMEOUT,
    )
    return lock if lock.acquire(blocking=False) else None


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

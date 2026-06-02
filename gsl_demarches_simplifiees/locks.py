import logging
from contextlib import contextmanager

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


@contextmanager
def demarche_sync_lock(demarche_number, timeout):
    """Verrou Redis non bloquant, par démarche, pour la sync des dossiers.

    Yield True si le verrou a été acquis, False s'il est déjà détenu
    (une autre sync de la même démarche tourne déjà).

    `timeout` est le TTL (secondes) du verrou : court pour une sync
    incrémentale depuis le dernier curseur, long pour une réinitialisation
    complète qui repart d'une date passée. Les deux partagent la même clé,
    donc s'excluent mutuellement quel que soit leur TTL.
    """
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    lock = client.lock(
        f"ds:demarche-sync:{demarche_number}",
        timeout=timeout,
    )
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except redis.exceptions.LockError:
                # Le TTL a expiré avant la fin de la sync : le verrou ne nous
                # appartient plus. On laisse passer (try étroit, type ciblé).
                logger.warning(
                    "DS sync lock for demarche %s expired before release "
                    "(sync longer than DS_SYNC_LOCK_TIMEOUT?)",
                    demarche_number,
                )

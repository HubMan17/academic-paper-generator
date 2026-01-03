import logging
import time
from contextlib import contextmanager
from typing import Generator
from uuid import UUID

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

LOCK_PREFIX = "pipeline:lock:"
DEFAULT_LOCK_TTL = 600
LOCK_ACQUIRE_TIMEOUT = 5


class LockAcquisitionError(Exception):
    pass


@contextmanager
def step_lock(
    document_id: UUID,
    kind: str,
    ttl: int = DEFAULT_LOCK_TTL,
    timeout: int = LOCK_ACQUIRE_TIMEOUT,
) -> Generator[bool, None, None]:
    lock_key = f"{LOCK_PREFIX}{document_id}:{kind}"
    lock_value = f"{time.time()}"
    acquired = False
    start_time = time.time()

    while time.time() - start_time < timeout:
        acquired = cache.add(lock_key, lock_value, ttl)
        if acquired:
            break
        time.sleep(0.1)

    if not acquired:
        existing = cache.get(lock_key)
        logger.warning(f"Could not acquire lock {lock_key}, existing: {existing}")

    try:
        yield acquired
    finally:
        if acquired:
            current_value = cache.get(lock_key)
            if current_value == lock_value:
                cache.delete(lock_key)


def try_acquire_lock(
    document_id: UUID,
    kind: str,
    ttl: int = DEFAULT_LOCK_TTL,
) -> bool:
    lock_key = f"{LOCK_PREFIX}{document_id}:{kind}"
    lock_value = f"{time.time()}"
    return cache.add(lock_key, lock_value, ttl)


def release_lock(document_id: UUID, kind: str) -> None:
    lock_key = f"{LOCK_PREFIX}{document_id}:{kind}"
    cache.delete(lock_key)


def is_locked(document_id: UUID, kind: str) -> bool:
    lock_key = f"{LOCK_PREFIX}{document_id}:{kind}"
    return cache.get(lock_key) is not None

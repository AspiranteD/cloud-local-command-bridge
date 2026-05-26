"""Database-based distributed lock for coordinating multiple bridge instances.

Prevents multiple instances from processing the same command simultaneously.
Uses an in-memory store for demonstration; swap with DB adapter in production.
"""

import time
import uuid
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LockRecord:
    """Record representing a held lock."""
    lock_key: str
    owner: str
    acquired_at: float
    expires_at: float


class LockStore:
    """In-memory lock store. Replace with DB adapter in production."""

    def __init__(self):
        self._locks: dict[str, LockRecord] = {}

    def try_acquire(self, key: str, owner: str, ttl: float) -> bool:
        now = time.time()
        existing = self._locks.get(key)

        if existing is not None:
            if existing.expires_at > now:
                return False
            logger.info(f"Lock '{key}' expired (owner={existing.owner}), reclaiming")

        self._locks[key] = LockRecord(
            lock_key=key,
            owner=owner,
            acquired_at=now,
            expires_at=now + ttl,
        )
        return True

    def release(self, key: str, owner: str) -> bool:
        existing = self._locks.get(key)
        if existing is None:
            return False
        if existing.owner != owner:
            return False
        del self._locks[key]
        return True

    def get_owner(self, key: str) -> Optional[str]:
        record = self._locks.get(key)
        if record is None:
            return None
        if record.expires_at <= time.time():
            del self._locks[key]
            return None
        return record.owner

    def is_locked(self, key: str) -> bool:
        return self.get_owner(key) is not None


class DistributedLock:
    """Distributed lock with expiry and owner tracking.

    Args:
        store: Lock store backend.
        key: The lock key to acquire.
        ttl: Time-to-live in seconds before auto-release (default 60).
        owner: Unique owner identifier (auto-generated if not provided).
    """

    def __init__(
        self,
        store: LockStore,
        key: str,
        ttl: float = 60.0,
        owner: Optional[str] = None,
    ):
        self._store = store
        self._key = key
        self._ttl = ttl
        self._owner = owner or str(uuid.uuid4())
        self._acquired = False

    @property
    def key(self) -> str:
        return self._key

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def is_acquired(self) -> bool:
        return self._acquired

    def acquire(self, timeout: float = 0, retry_interval: float = 0.1) -> bool:
        """Attempt to acquire the lock.

        Args:
            timeout: Max seconds to wait (0 = single attempt).
            retry_interval: Seconds between retry attempts.

        Returns:
            True if acquired, False otherwise.
        """
        deadline = time.time() + timeout

        while True:
            if self._store.try_acquire(self._key, self._owner, self._ttl):
                self._acquired = True
                logger.info(f"Lock '{self._key}' acquired by {self._owner}")
                return True

            if time.time() >= deadline:
                return False

            time.sleep(retry_interval)

    def release(self) -> bool:
        """Release the lock.

        Returns:
            True if released, False if not held by this owner.
        """
        if not self._acquired:
            return False
        released = self._store.release(self._key, self._owner)
        if released:
            self._acquired = False
            logger.info(f"Lock '{self._key}' released by {self._owner}")
        return released

    def __enter__(self) -> "DistributedLock":
        if not self.acquire():
            raise RuntimeError(
                f"Failed to acquire lock '{self._key}' "
                f"(held by {self._store.get_owner(self._key)})"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

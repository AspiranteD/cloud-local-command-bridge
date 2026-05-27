"""
Distributed lock with heartbeat and automatic failover.

Ensures only one backend instance processes commands at a time.
If the active instance dies (heartbeat stops), another can take
over after LOCK_TIMEOUT seconds.

Database-agnostic: uses callback functions for persistence.
"""
import os
import socket
import time
from dataclasses import dataclass
from typing import Optional, Callable


HEARTBEAT_INTERVAL = 10
LOCK_TIMEOUT = 60
LOCK_RETRY_INTERVAL = 30
SAME_HOST_RETRY_INTERVAL = 10


def get_instance_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def get_hostname() -> str:
    return socket.gethostname()


@dataclass
class LockState:
    locked_by: Optional[str] = None
    instance_id: Optional[str] = None
    heartbeat_at: Optional[float] = None

    @property
    def is_held(self) -> bool:
        return self.locked_by is not None

    @property
    def is_expired(self) -> bool:
        if not self.heartbeat_at:
            return True
        return (time.time() - self.heartbeat_at) > LOCK_TIMEOUT

    def is_same_host(self, hostname: str) -> bool:
        return self.locked_by == hostname

    def is_same_host_stale(self, hostname: str) -> bool:
        """True if same host but heartbeat older than SAME_HOST_RETRY_INTERVAL."""
        if not self.is_same_host(hostname):
            return False
        if not self.heartbeat_at:
            return True
        return (time.time() - self.heartbeat_at) > SAME_HOST_RETRY_INTERVAL


@dataclass
class LockCallbacks:
    """Callbacks for lock persistence operations."""
    read_lock: Callable[[], LockState] = None
    try_acquire: Callable[[str, str], bool] = None
    send_heartbeat: Callable[[str], bool] = None
    release: Callable[[str], None] = None


class DistributedLock:
    def __init__(self, callbacks: LockCallbacks):
        self.instance_id = get_instance_id()
        self.hostname = get_hostname()
        self.is_active = False
        self._cb = callbacks
        self._last_heartbeat: float = 0

    def try_acquire(self) -> bool:
        """
        Attempt to acquire the lock.

        Succeeds if:
        - No one holds it
        - Current holder's heartbeat expired (> LOCK_TIMEOUT)
        - Same hostname with stale heartbeat (process restart)
        """
        current = self._cb.read_lock()

        if not current.is_held:
            acquired = self._cb.try_acquire(self.hostname, self.instance_id)
            if acquired:
                self.is_active = True
            return acquired

        if current.is_expired:
            acquired = self._cb.try_acquire(self.hostname, self.instance_id)
            if acquired:
                self.is_active = True
            return acquired

        if current.is_same_host_stale(self.hostname):
            acquired = self._cb.try_acquire(self.hostname, self.instance_id)
            if acquired:
                self.is_active = True
            return acquired

        return False

    def send_heartbeat(self) -> bool:
        """Update heartbeat. Returns False if we lost the lock."""
        if not self.is_active:
            return False
        now = time.time()
        if (now - self._last_heartbeat) < HEARTBEAT_INTERVAL:
            return True
        still_mine = self._cb.send_heartbeat(self.instance_id)
        if still_mine:
            self._last_heartbeat = now
        else:
            self.is_active = False
        return still_mine

    def release(self) -> None:
        if self.is_active:
            self._cb.release(self.instance_id)
            self.is_active = False

    def get_holder_info(self) -> str:
        current = self._cb.read_lock()
        if current.is_held:
            return f"{current.locked_by} (heartbeat: {current.heartbeat_at})"
        return "nobody (lock free)"

    def compute_retry_interval(self) -> int:
        """Shorter retry if same hostname (likely restart)."""
        current = self._cb.read_lock()
        if current.is_same_host(self.hostname):
            return SAME_HOST_RETRY_INTERVAL
        return LOCK_RETRY_INTERVAL

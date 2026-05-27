"""
Printer discovery with TTL-based caching.

Avoids hitting OS-level printer detection (USB/PowerShell) every poll cycle.
After a successful detection, caches the result for CACHE_TTL seconds.
Failed detections are never cached (retry immediately next cycle).

Also handles printer heartbeat registration: each PC with a printer
registers its availability so the cloud UI can list available printers.
"""
import time
from dataclasses import dataclass
from typing import Callable


CACHE_TTL = 60
HEARTBEAT_INTERVAL = 30


@dataclass
class PrinterState:
    detected: bool = False
    cache_ts: float = 0.0
    heartbeat_ts: float = 0.0
    hostname: str = ""


class PrinterCallbacks:
    def __init__(
        self,
        detect_printer: Callable[[], bool] = None,
        send_heartbeat: Callable[[str], None] = None,
    ):
        self.detect_printer = detect_printer
        self.send_heartbeat = send_heartbeat


class PrinterDiscovery:
    def __init__(
        self,
        callbacks: PrinterCallbacks,
        hostname: str = "",
        cache_ttl: int = CACHE_TTL,
        heartbeat_interval: int = HEARTBEAT_INTERVAL,
    ):
        self._cb = callbacks
        self._state = PrinterState(hostname=hostname)
        self._cache_ttl = cache_ttl
        self._heartbeat_interval = heartbeat_interval

    @property
    def is_available(self) -> bool:
        return self._state.detected

    def check_cached(self) -> bool:
        """
        Check printer availability with caching.

        Successful detections are cached for cache_ttl seconds.
        Failed detections clear the cache (retry next cycle).
        """
        now = time.monotonic()

        if self._state.detected and (now - self._state.cache_ts) < self._cache_ttl:
            return True

        available = self._cb.detect_printer()

        if available:
            self._state.detected = True
            self._state.cache_ts = now
        else:
            self._state.detected = False
            self._state.cache_ts = 0.0

        return available

    def send_heartbeat_if_due(self) -> bool:
        """Send printer heartbeat if enough time has passed. Returns True if sent."""
        if not self._state.detected:
            return False

        now = time.monotonic()
        if (now - self._state.heartbeat_ts) < self._heartbeat_interval:
            return False

        self._state.heartbeat_ts = now
        if self._cb.send_heartbeat:
            self._cb.send_heartbeat(self._state.hostname)
        return True

    def invalidate_cache(self) -> None:
        """Force re-detection on next check (e.g., after printer error)."""
        self._state.detected = False
        self._state.cache_ts = 0.0

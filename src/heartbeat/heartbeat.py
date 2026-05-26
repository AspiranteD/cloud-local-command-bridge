"""Heartbeat reporter for bridge health monitoring.

Periodically reports status so the cloud side can detect dead bridges.
"""

import time
import platform
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatPayload:
    """Data sent with each heartbeat."""
    timestamp: str
    hostname: str
    uptime_seconds: float
    commands_processed: int
    current_command: Optional[str] = None


class HeartbeatStore:
    """In-memory heartbeat store. Replace with DB adapter in production."""

    def __init__(self):
        self.beats: list[HeartbeatPayload] = []

    def save(self, payload: HeartbeatPayload) -> None:
        self.beats.append(payload)

    def get_latest(self) -> Optional[HeartbeatPayload]:
        return self.beats[-1] if self.beats else None


class HeartbeatReporter:
    """Periodically reports bridge health status.

    Args:
        store: Backend store for heartbeat records.
        interval: Seconds between heartbeats (default 30).
        commands_counter: Callable returning current processed command count.
        current_command_getter: Callable returning current command name or None.
    """

    def __init__(
        self,
        store: HeartbeatStore,
        interval: float = 30.0,
        commands_counter: Optional[Callable[[], int]] = None,
        current_command_getter: Optional[Callable[[], Optional[str]]] = None,
    ):
        self._store = store
        self._interval = interval
        self._commands_counter = commands_counter or (lambda: 0)
        self._current_command_getter = current_command_getter or (lambda: None)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._start_time = time.monotonic()
        self._hostname = platform.node()

    @property
    def interval(self) -> float:
        return self._interval

    @property
    def is_running(self) -> bool:
        return self._running

    def _build_payload(self) -> HeartbeatPayload:
        return HeartbeatPayload(
            timestamp=datetime.now(timezone.utc).isoformat(),
            hostname=self._hostname,
            uptime_seconds=round(time.monotonic() - self._start_time, 2),
            commands_processed=self._commands_counter(),
            current_command=self._current_command_getter(),
        )

    def report_now(self) -> HeartbeatPayload:
        """Send a heartbeat immediately."""
        payload = self._build_payload()
        self._store.save(payload)
        logger.debug(f"Heartbeat: uptime={payload.uptime_seconds}s, cmds={payload.commands_processed}")
        return payload

    def start(self) -> None:
        """Start the background heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"Heartbeat started (interval={self._interval}s)")

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1)
            self._thread = None
        logger.info("Heartbeat stopped")

    def _loop(self) -> None:
        while self._running:
            try:
                self.report_now()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            time.sleep(self._interval)

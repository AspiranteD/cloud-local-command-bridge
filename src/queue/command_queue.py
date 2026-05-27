"""
Command queue with claim-execute-update pattern.

Commands flow: pending -> processing -> done/error
Uses FOR UPDATE SKIP LOCKED semantics (simulated via callbacks)
to allow concurrent workers without double-processing.

Supports command TTL expiration and requeue on transient failures.
"""
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any


COMMAND_TTL = 120


@dataclass
class Command:
    id: int
    command: str
    params: dict = field(default_factory=dict)
    created_by: str = "unknown"
    created_at: float = 0
    status: str = "pending"

    @property
    def is_expired(self) -> bool:
        if self.created_at <= 0:
            return False
        return (time.time() - self.created_at) > COMMAND_TTL


@dataclass
class CommandResult:
    command_id: int
    status: str
    result: dict = field(default_factory=dict)


class QueueCallbacks:
    """Callbacks for queue persistence."""
    def __init__(
        self,
        claim_next: Callable[[list[str]], Optional[Command]] = None,
        update_status: Callable[[int, str, dict], None] = None,
        cancel_pending: Callable[[list[str]], int] = None,
        expire_old: Callable[[list[str], int], int] = None,
        requeue: Callable[[int], None] = None,
        count_pending: Callable[[list[str]], int] = None,
    ):
        self.claim_next = claim_next
        self.update_status = update_status
        self.cancel_pending = cancel_pending
        self.expire_old = expire_old
        self.requeue = requeue
        self.count_pending = count_pending


class CommandQueue:
    def __init__(self, callbacks: QueueCallbacks, ttl: int = COMMAND_TTL):
        self._cb = callbacks
        self.ttl = ttl

    def claim_next(self, exclude_commands: list[str] = None) -> Optional[Command]:
        """Claim the next pending command (skip locked by other workers)."""
        return self._cb.claim_next(exclude_commands or [])

    def mark_done(self, cmd_id: int, result: dict) -> CommandResult:
        self._cb.update_status(cmd_id, "done", result)
        return CommandResult(command_id=cmd_id, status="done", result=result)

    def mark_error(self, cmd_id: int, error: str) -> CommandResult:
        result = {"error": error}
        self._cb.update_status(cmd_id, "error", result)
        return CommandResult(command_id=cmd_id, status="error", result=result)

    def requeue(self, cmd_id: int) -> None:
        """Return a command to pending (e.g., printer not available, retry later)."""
        self._cb.requeue(cmd_id)

    def cancel_pending(self, exclude_commands: list[str] = None) -> int:
        """Cancel all pending commands (graceful shutdown). Returns count."""
        return self._cb.cancel_pending(exclude_commands or [])

    def expire_old(self, command_filter: list[str] = None) -> int:
        """Expire commands older than TTL. Returns count."""
        return self._cb.expire_old(command_filter or [], self.ttl)

    def count_pending(self, command_filter: list[str] = None) -> int:
        return self._cb.count_pending(command_filter or [])

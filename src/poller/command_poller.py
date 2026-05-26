"""Command poller that fetches pending commands from a queue.

Designed to work with a database-backed queue in production,
but uses an in-memory implementation for demonstration.
"""

import signal
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CommandStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Command:
    id: str
    name: str
    params: dict = field(default_factory=dict)
    status: CommandStatus = CommandStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class CommandQueue:
    """In-memory command queue. Replace with DB adapter in production."""

    def __init__(self):
        self._commands: dict[str, Command] = {}

    def push(self, command: Command) -> None:
        self._commands[command.id] = command

    def get_oldest_pending(self) -> Optional[Command]:
        pending = [
            cmd for cmd in self._commands.values()
            if cmd.status == CommandStatus.PENDING
        ]
        if not pending:
            return None
        return min(pending, key=lambda c: c.created_at)

    def update(self, command: Command) -> None:
        self._commands[command.id] = command

    def get(self, command_id: str) -> Optional[Command]:
        return self._commands.get(command_id)


class CommandPoller:
    """Polls a command queue for pending commands and dispatches execution.

    Args:
        queue: The command queue to poll from.
        executor: Callable that executes a command and returns a result.
        poll_interval: Seconds between polls (default 5).
    """

    def __init__(
        self,
        queue: CommandQueue,
        executor: Optional[Callable[[str, dict], Any]] = None,
        poll_interval: float = 5.0,
    ):
        self._queue = queue
        self._executor = executor
        self._poll_interval = poll_interval
        self._running = False
        self._commands_processed = 0

    @property
    def poll_interval(self) -> float:
        return self._poll_interval

    @property
    def commands_processed(self) -> int:
        return self._commands_processed

    @property
    def is_running(self) -> bool:
        return self._running

    def poll(self) -> Optional[Command]:
        """Fetch the oldest pending command from the queue."""
        return self._queue.get_oldest_pending()

    def acknowledge(self, command_id: str) -> None:
        """Mark a command as in-progress."""
        command = self._queue.get(command_id)
        if command is None:
            raise ValueError(f"Command {command_id} not found")
        command.status = CommandStatus.IN_PROGRESS
        command.started_at = datetime.now(timezone.utc)
        self._queue.update(command)
        logger.info(f"Command {command_id} acknowledged")

    def complete(self, command_id: str, result: Any) -> None:
        """Mark a command as completed with result."""
        command = self._queue.get(command_id)
        if command is None:
            raise ValueError(f"Command {command_id} not found")
        command.status = CommandStatus.COMPLETED
        command.result = result
        command.completed_at = datetime.now(timezone.utc)
        self._queue.update(command)
        self._commands_processed += 1
        logger.info(f"Command {command_id} completed")

    def fail(self, command_id: str, error: str) -> None:
        """Mark a command as failed with error."""
        command = self._queue.get(command_id)
        if command is None:
            raise ValueError(f"Command {command_id} not found")
        command.status = CommandStatus.FAILED
        command.error = error
        command.completed_at = datetime.now(timezone.utc)
        self._queue.update(command)
        self._commands_processed += 1
        logger.info(f"Command {command_id} failed: {error}")

    def _process_one(self) -> bool:
        """Process a single command. Returns True if a command was processed."""
        command = self.poll()
        if command is None:
            return False

        self.acknowledge(command.id)

        if self._executor is None:
            self.fail(command.id, "No executor configured")
            return True

        try:
            result = self._executor(command.name, command.params)
            self.complete(command.id, result)
        except Exception as e:
            self.fail(command.id, str(e))

        return True

    def run_forever(self) -> None:
        """Main loop: poll → execute → report. Stops on SIGINT/SIGTERM."""
        self._running = True

        def _shutdown(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self._running = False

        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        logger.info(f"Poller started (interval={self._poll_interval}s)")

        try:
            while self._running:
                try:
                    self._process_one()
                except Exception as e:
                    logger.error(f"Unexpected error in poll loop: {e}")
                time.sleep(self._poll_interval)
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
            self._running = False
            logger.info("Poller stopped")

    def stop(self) -> None:
        """Signal the poller to stop."""
        self._running = False

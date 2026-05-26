"""Command executor that runs registered commands with timeout and isolation."""

import io
import sys
import logging
import threading
from typing import Any, Optional
from dataclasses import dataclass

from .command_registry import CommandRegistry

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a command execution."""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class CommandExecutor:
    """Executes registered commands with timeout support and output capture.

    Args:
        registry: The command registry containing allowed commands.
    """

    def __init__(self, registry: CommandRegistry):
        self._registry = registry

    @property
    def registry(self) -> CommandRegistry:
        return self._registry

    def execute(self, command_name: str, params: Optional[dict] = None) -> ExecutionResult:
        """Run a registered command by name.

        Args:
            command_name: Name of the command to execute.
            params: Parameters to pass to the command handler.

        Returns:
            ExecutionResult with captured output or error.

        Raises:
            KeyError: If the command is not registered.
        """
        params = params or {}
        entry = self._registry.get_command(command_name)

        import time
        start = time.monotonic()

        stdout_capture = io.StringIO()
        result_container: dict[str, Any] = {}
        error_container: dict[str, Any] = {}

        def _run():
            old_stdout = sys.stdout
            sys.stdout = stdout_capture
            try:
                result_container["value"] = entry.handler(**params)
            except Exception as e:
                error_container["value"] = e
            finally:
                sys.stdout = old_stdout

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=entry.timeout)

        duration_ms = (time.monotonic() - start) * 1000

        if thread.is_alive():
            return ExecutionResult(
                success=False,
                error=f"Command '{command_name}' timed out after {entry.timeout}s",
                duration_ms=duration_ms,
            )

        if "value" in error_container:
            return ExecutionResult(
                success=False,
                error=str(error_container["value"]),
                output=stdout_capture.getvalue() or None,
                duration_ms=duration_ms,
            )

        output = stdout_capture.getvalue() or None
        result_value = result_container.get("value")

        if result_value is not None and output is None:
            output = str(result_value)

        return ExecutionResult(
            success=True,
            output=output,
            duration_ms=duration_ms,
        )

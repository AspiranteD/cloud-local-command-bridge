"""Registry of allowed commands for the bridge.

Only commands explicitly registered here can be executed,
preventing arbitrary code execution.
"""

import platform
import time
from dataclasses import dataclass
from typing import Callable, Any

DEFAULT_TIMEOUT = 30.0


@dataclass
class CommandEntry:
    """A registered command entry."""
    name: str
    handler: Callable[..., Any]
    timeout: float
    description: str


class CommandRegistry:
    """Registry of allowed commands. Only registered commands can execute.

    Args:
        include_builtins: Whether to register built-in commands (default True).
    """

    def __init__(self, include_builtins: bool = True):
        self._commands: dict[str, CommandEntry] = {}
        if include_builtins:
            self._register_builtins()

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        timeout: float = DEFAULT_TIMEOUT,
        description: str = "",
    ) -> None:
        """Register a command handler.

        Args:
            name: Unique command name (case-insensitive, stored uppercase).
            handler: Callable that executes the command.
            timeout: Max execution time in seconds.
            description: Human-readable description.
        """
        key = name.upper()
        self._commands[key] = CommandEntry(
            name=key,
            handler=handler,
            timeout=timeout,
            description=description,
        )

    def get_command(self, name: str) -> CommandEntry:
        """Get a registered command by name.

        Raises:
            KeyError: If the command is not registered.
        """
        key = name.upper()
        if key not in self._commands:
            raise KeyError(
                f"Command '{name}' is not registered. "
                f"Available: {list(self._commands.keys())}"
            )
        return self._commands[key]

    def list_commands(self) -> list[dict[str, str]]:
        """List all registered commands with their descriptions."""
        return [
            {"name": entry.name, "description": entry.description}
            for entry in self._commands.values()
        ]

    def has_command(self, name: str) -> bool:
        """Check if a command is registered."""
        return name.upper() in self._commands

    def _register_builtins(self) -> None:
        """Register built-in commands."""
        self.register(
            "PING",
            handler=_builtin_ping,
            timeout=5.0,
            description="Health check - returns PONG",
        )
        self.register(
            "STATUS",
            handler=_builtin_status,
            timeout=10.0,
            description="Returns bridge status information",
        )
        self.register(
            "RESTART",
            handler=_builtin_restart,
            timeout=5.0,
            description="Signals the bridge to restart (graceful)",
        )


def _builtin_ping() -> str:
    return "PONG"


def _builtin_status() -> dict:
    return {
        "status": "running",
        "platform": platform.system(),
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "uptime_check": time.monotonic(),
    }


def _builtin_restart() -> str:
    return "RESTART_SCHEDULED"

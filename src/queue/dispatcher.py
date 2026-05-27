"""
Command dispatcher: routes commands to handler functions.

Supports synchronous and async handlers, with extensible
command registration.
"""
from dataclasses import dataclass
from typing import Callable, Optional, Any


@dataclass
class DispatchResult:
    command: str
    success: bool
    result: dict


class CommandDispatcher:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, command: str, handler: Callable) -> None:
        """Register a handler function for a command name."""
        self._handlers[command] = handler

    def register_many(self, handlers: dict[str, Callable]) -> None:
        self._handlers.update(handlers)

    def can_dispatch(self, command: str) -> bool:
        return command in self._handlers

    @property
    def registered_commands(self) -> list[str]:
        return sorted(self._handlers.keys())

    def dispatch(self, command: str, params: dict) -> DispatchResult:
        """
        Dispatch a command to its registered handler.

        Returns DispatchResult with success=False if command unknown
        or handler raises an exception.
        """
        handler = self._handlers.get(command)
        if handler is None:
            return DispatchResult(
                command=command, success=False,
                result={"error": f"Unknown command: {command}"},
            )
        try:
            result = handler(params)
            if not isinstance(result, dict):
                result = {"result": result}
            is_error = "error" in result
            return DispatchResult(
                command=command, success=not is_error, result=result,
            )
        except Exception as e:
            return DispatchResult(
                command=command, success=False,
                result={"error": str(e)},
            )

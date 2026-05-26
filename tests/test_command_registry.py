"""Tests for CommandRegistry."""

import pytest

from src.executor.command_registry import CommandRegistry, CommandEntry


class TestCommandRegistry:
    def test_register_and_get_command(self):
        registry = CommandRegistry(include_builtins=False)
        registry.register("TEST", handler=lambda: None, description="A test")
        entry = registry.get_command("TEST")
        assert entry.name == "TEST"
        assert entry.description == "A test"

    def test_case_insensitive_lookup(self):
        registry = CommandRegistry(include_builtins=False)
        registry.register("MyCommand", handler=lambda: None, description="Mixed case")
        entry = registry.get_command("mycommand")
        assert entry.name == "MYCOMMAND"

    def test_get_unregistered_raises_keyerror(self):
        registry = CommandRegistry(include_builtins=False)
        with pytest.raises(KeyError, match="not registered"):
            registry.get_command("MISSING")

    def test_list_commands(self):
        registry = CommandRegistry(include_builtins=False)
        registry.register("A", handler=lambda: None, description="First")
        registry.register("B", handler=lambda: None, description="Second")
        commands = registry.list_commands()
        assert len(commands) == 2
        names = [c["name"] for c in commands]
        assert "A" in names
        assert "B" in names

    def test_has_command(self):
        registry = CommandRegistry(include_builtins=False)
        registry.register("EXISTS", handler=lambda: None, description="Yes")
        assert registry.has_command("EXISTS") is True
        assert registry.has_command("NOPE") is False

    def test_builtin_ping(self):
        registry = CommandRegistry(include_builtins=True)
        entry = registry.get_command("PING")
        assert entry.handler() == "PONG"

    def test_builtin_status(self):
        registry = CommandRegistry(include_builtins=True)
        entry = registry.get_command("STATUS")
        result = entry.handler()
        assert result["status"] == "running"
        assert "hostname" in result

    def test_builtin_restart(self):
        registry = CommandRegistry(include_builtins=True)
        entry = registry.get_command("RESTART")
        assert entry.handler() == "RESTART_SCHEDULED"

    def test_custom_timeout(self):
        registry = CommandRegistry(include_builtins=False)
        registry.register("SLOW", handler=lambda: None, timeout=120.0, description="Slow")
        entry = registry.get_command("SLOW")
        assert entry.timeout == 120.0

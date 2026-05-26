"""Tests for CommandExecutor."""

import time
import pytest

from src.executor.command_executor import CommandExecutor, ExecutionResult
from src.executor.command_registry import CommandRegistry


@pytest.fixture
def registry():
    return CommandRegistry(include_builtins=False)


@pytest.fixture
def executor(registry):
    return CommandExecutor(registry=registry)


class TestCommandExecutor:
    def test_execute_simple_command(self, executor, registry):
        registry.register("HELLO", handler=lambda: "world", description="Test")
        result = executor.execute("HELLO")
        assert result.success is True
        assert result.output == "world"

    def test_execute_with_params(self, executor, registry):
        registry.register("ADD", handler=lambda a, b: a + b, description="Add")
        result = executor.execute("ADD", {"a": 2, "b": 3})
        assert result.success is True
        assert result.output == "5"

    def test_execute_captures_stdout(self, executor, registry):
        def noisy():
            print("hello from stdout")
            return None

        registry.register("NOISY", handler=noisy, description="Noisy")
        result = executor.execute("NOISY")
        assert result.success is True
        assert "hello from stdout" in result.output

    def test_execute_handles_exception(self, executor, registry):
        def failing():
            raise RuntimeError("intentional failure")

        registry.register("FAIL", handler=failing, description="Fails")
        result = executor.execute("FAIL")
        assert result.success is False
        assert "intentional failure" in result.error

    def test_execute_timeout(self, executor, registry):
        def slow():
            time.sleep(5)
            return "done"

        registry.register("SLOW", handler=slow, timeout=0.1, description="Slow")
        result = executor.execute("SLOW")
        assert result.success is False
        assert "timed out" in result.error

    def test_execute_unregistered_command_raises(self, executor):
        with pytest.raises(KeyError):
            executor.execute("NONEXISTENT")

    def test_execution_result_has_duration(self, executor, registry):
        registry.register("FAST", handler=lambda: "quick", description="Fast")
        result = executor.execute("FAST")
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

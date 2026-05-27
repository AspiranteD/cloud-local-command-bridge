"""Tests for command dispatcher."""
import pytest
from src.queue.dispatcher import CommandDispatcher, DispatchResult


class TestDispatcher:
    def test_register_and_dispatch(self):
        d = CommandDispatcher()
        d.register("greet", lambda p: {"msg": f"Hello {p.get('name')}"})
        result = d.dispatch("greet", {"name": "World"})
        assert result.success
        assert result.result["msg"] == "Hello World"

    def test_unknown_command(self):
        d = CommandDispatcher()
        result = d.dispatch("nonexistent", {})
        assert not result.success
        assert "Unknown command" in result.result["error"]

    def test_handler_exception(self):
        d = CommandDispatcher()
        d.register("fail", lambda p: 1 / 0)
        result = d.dispatch("fail", {})
        assert not result.success
        assert "division by zero" in result.result["error"]

    def test_handler_returns_error_dict(self):
        d = CommandDispatcher()
        d.register("bad", lambda p: {"error": "invalid param"})
        result = d.dispatch("bad", {})
        assert not result.success
        assert result.result["error"] == "invalid param"

    def test_handler_returns_non_dict(self):
        d = CommandDispatcher()
        d.register("count", lambda p: 42)
        result = d.dispatch("count", {})
        assert result.success
        assert result.result["result"] == 42

    def test_register_many(self):
        d = CommandDispatcher()
        d.register_many({
            "a": lambda p: {"ok": True},
            "b": lambda p: {"ok": True},
        })
        assert d.can_dispatch("a")
        assert d.can_dispatch("b")
        assert not d.can_dispatch("c")

    def test_registered_commands(self):
        d = CommandDispatcher()
        d.register("start", lambda p: {})
        d.register("stop", lambda p: {})
        assert d.registered_commands == ["start", "stop"]


class TestDispatchResult:
    def test_success(self):
        r = DispatchResult(command="test", success=True, result={"ok": True})
        assert r.command == "test"
        assert r.success

    def test_failure(self):
        r = DispatchResult(command="test", success=False, result={"error": "fail"})
        assert not r.success


# ─── Real-world command patterns ─────────────────────────────────────

class TestRealWorldPatterns:
    def setup_method(self):
        self.d = CommandDispatcher()
        self._scheduler_running = False

        def start_scheduler(params):
            if self._scheduler_running:
                return {"message": "Scheduler already running"}
            self._scheduler_running = True
            return {"message": "Scheduler started"}

        def stop_scheduler(params):
            if not self._scheduler_running:
                return {"message": "Scheduler already stopped"}
            self._scheduler_running = False
            return {"message": "Scheduler stopped"}

        def run_job(params):
            job_id = params.get("job_id", "")
            valid = {"extract_orders", "extract_chats", "extract_listings"}
            if job_id not in valid:
                return {"error": f"Invalid job: {job_id}"}
            if not self._scheduler_running:
                return {"error": "Scheduler not running"}
            return {"message": f"{job_id} scheduled"}

        def set_interval(params):
            job_id = params.get("job_id")
            hours = params.get("hours", 1)
            minutes = params.get("minutes", 0)
            if hours == 0 and minutes == 0:
                return {"error": "Interval cannot be zero"}
            return {"message": f"{job_id} interval set to {hours}h {minutes}m"}

        self.d.register_many({
            "start_scheduler": start_scheduler,
            "stop_scheduler": stop_scheduler,
            "run_job": run_job,
            "set_interval": set_interval,
        })

    def test_start_scheduler(self):
        r = self.d.dispatch("start_scheduler", {})
        assert r.success
        assert "started" in r.result["message"]

    def test_start_twice(self):
        self.d.dispatch("start_scheduler", {})
        r = self.d.dispatch("start_scheduler", {})
        assert r.success
        assert "already" in r.result["message"]

    def test_run_job_valid(self):
        self.d.dispatch("start_scheduler", {})
        r = self.d.dispatch("run_job", {"job_id": "extract_orders"})
        assert r.success

    def test_run_job_invalid(self):
        self.d.dispatch("start_scheduler", {})
        r = self.d.dispatch("run_job", {"job_id": "bogus"})
        assert not r.success

    def test_run_job_scheduler_not_running(self):
        r = self.d.dispatch("run_job", {"job_id": "extract_orders"})
        assert not r.success

    def test_set_interval_valid(self):
        r = self.d.dispatch("set_interval", {"job_id": "x", "hours": 2})
        assert r.success

    def test_set_interval_zero(self):
        r = self.d.dispatch("set_interval", {"job_id": "x", "hours": 0, "minutes": 0})
        assert not r.success

    def test_stop_scheduler(self):
        self.d.dispatch("start_scheduler", {})
        r = self.d.dispatch("stop_scheduler", {})
        assert r.success
        assert "stopped" in r.result["message"]

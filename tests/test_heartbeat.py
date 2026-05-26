"""Tests for HeartbeatReporter."""

import time
import pytest

from src.heartbeat.heartbeat import HeartbeatReporter, HeartbeatStore


@pytest.fixture
def store():
    return HeartbeatStore()


@pytest.fixture
def reporter(store):
    return HeartbeatReporter(store=store, interval=0.1)


class TestHeartbeatReporter:
    def test_report_now(self, reporter, store):
        payload = reporter.report_now()
        assert payload.hostname != ""
        assert payload.uptime_seconds >= 0
        assert store.get_latest() is payload

    def test_heartbeat_contains_timestamp(self, reporter):
        payload = reporter.report_now()
        assert "T" in payload.timestamp  # ISO format

    def test_commands_counter_integration(self, store):
        counter = {"value": 5}
        reporter = HeartbeatReporter(
            store=store,
            commands_counter=lambda: counter["value"],
        )
        payload = reporter.report_now()
        assert payload.commands_processed == 5

    def test_current_command_reporting(self, store):
        reporter = HeartbeatReporter(
            store=store,
            current_command_getter=lambda: "IMPORT_DATA",
        )
        payload = reporter.report_now()
        assert payload.current_command == "IMPORT_DATA"

    def test_start_and_stop(self, reporter, store):
        reporter.start()
        assert reporter.is_running is True
        time.sleep(0.25)
        reporter.stop()
        assert reporter.is_running is False
        assert len(store.beats) >= 2

    def test_multiple_start_calls_idempotent(self, reporter):
        reporter.start()
        reporter.start()
        assert reporter.is_running is True
        reporter.stop()

    def test_default_interval(self, store):
        reporter = HeartbeatReporter(store=store)
        assert reporter.interval == 30.0

    def test_custom_interval(self, store):
        reporter = HeartbeatReporter(store=store, interval=10.0)
        assert reporter.interval == 10.0

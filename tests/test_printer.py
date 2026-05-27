"""Tests for printer discovery with TTL cache."""
import time
import pytest
from unittest.mock import MagicMock
from src.printer.printer_discovery import (
    PrinterDiscovery, PrinterCallbacks, PrinterState,
    CACHE_TTL, HEARTBEAT_INTERVAL,
)


def _make_discovery(
    detect_result=True,
    hostname="test-pc",
    cache_ttl=CACHE_TTL,
    heartbeat_interval=HEARTBEAT_INTERVAL,
):
    heartbeats = []
    cb = PrinterCallbacks(
        detect_printer=lambda: detect_result,
        send_heartbeat=lambda h: heartbeats.append(h),
    )
    disc = PrinterDiscovery(
        cb, hostname=hostname,
        cache_ttl=cache_ttl,
        heartbeat_interval=heartbeat_interval,
    )
    return disc, heartbeats


# ─── check_cached ────────────────────────────────────────────────────

class TestCheckCached:
    def test_first_check_detects(self):
        disc, _ = _make_discovery(detect_result=True)
        assert disc.check_cached()
        assert disc.is_available

    def test_first_check_not_found(self):
        disc, _ = _make_discovery(detect_result=False)
        assert not disc.check_cached()
        assert not disc.is_available

    def test_cached_result(self):
        call_count = [0]

        def detect():
            call_count[0] += 1
            return True

        cb = PrinterCallbacks(detect_printer=detect)
        disc = PrinterDiscovery(cb, hostname="pc", cache_ttl=60)

        disc.check_cached()
        assert call_count[0] == 1

        disc.check_cached()
        assert call_count[0] == 1

    def test_cache_expired(self):
        call_count = [0]

        def detect():
            call_count[0] += 1
            return True

        cb = PrinterCallbacks(detect_printer=detect)
        disc = PrinterDiscovery(cb, hostname="pc", cache_ttl=0)

        disc.check_cached()
        assert call_count[0] == 1

        disc.check_cached()
        assert call_count[0] == 2

    def test_failed_detection_clears_cache(self):
        results = iter([True, False, True])
        cb = PrinterCallbacks(detect_printer=lambda: next(results))
        disc = PrinterDiscovery(cb, hostname="pc", cache_ttl=0)

        assert disc.check_cached()
        assert disc.is_available

        assert not disc.check_cached()
        assert not disc.is_available

        assert disc.check_cached()
        assert disc.is_available


# ─── send_heartbeat_if_due ──────────────────────────────────────────

class TestHeartbeat:
    def test_not_detected(self):
        disc, heartbeats = _make_discovery(detect_result=False)
        assert not disc.send_heartbeat_if_due()
        assert heartbeats == []

    def test_sends_first_time(self):
        disc, heartbeats = _make_discovery(detect_result=True, heartbeat_interval=0)
        disc.check_cached()
        assert disc.send_heartbeat_if_due()
        assert heartbeats == ["test-pc"]

    def test_throttled(self):
        disc, heartbeats = _make_discovery(
            detect_result=True, heartbeat_interval=9999,
        )
        disc.check_cached()
        disc.send_heartbeat_if_due()
        disc.send_heartbeat_if_due()
        assert len(heartbeats) == 1

    def test_no_callback(self):
        cb = PrinterCallbacks(detect_printer=lambda: True)
        disc = PrinterDiscovery(cb, hostname="pc", heartbeat_interval=0)
        disc.check_cached()
        assert disc.send_heartbeat_if_due()


# ─── invalidate_cache ────────────────────────────────────────────────

class TestInvalidateCache:
    def test_invalidate(self):
        disc, _ = _make_discovery(detect_result=True)
        disc.check_cached()
        assert disc.is_available

        disc.invalidate_cache()
        assert not disc.is_available


# ─── PrinterState ────────────────────────────────────────────────────

class TestPrinterState:
    def test_defaults(self):
        s = PrinterState()
        assert not s.detected
        assert s.hostname == ""

    def test_with_values(self):
        s = PrinterState(detected=True, hostname="my-pc")
        assert s.detected
        assert s.hostname == "my-pc"

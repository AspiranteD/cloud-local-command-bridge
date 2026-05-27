"""Tests for command queue with claim-execute-update pattern."""
import time
import pytest
from src.queue.command_queue import (
    CommandQueue, QueueCallbacks, Command, CommandResult, COMMAND_TTL,
)


def _make_queue(
    claim_return=None,
    cancel_count=0,
    expire_count=0,
    pending_count=0,
):
    updates = []
    requeues = []

    cb = QueueCallbacks(
        claim_next=lambda exclude: claim_return,
        update_status=lambda cid, s, r: updates.append((cid, s, r)),
        cancel_pending=lambda exclude: cancel_count,
        expire_old=lambda filt, ttl: expire_count,
        requeue=lambda cid: requeues.append(cid),
        count_pending=lambda filt: pending_count,
    )
    return CommandQueue(cb), updates, requeues


# ─── Command dataclass ───────────────────────────────────────────────

class TestCommand:
    def test_not_expired(self):
        cmd = Command(id=1, command="test", created_at=time.time())
        assert not cmd.is_expired

    def test_expired(self):
        cmd = Command(id=1, command="test", created_at=time.time() - COMMAND_TTL - 1)
        assert cmd.is_expired

    def test_no_created_at(self):
        cmd = Command(id=1, command="test")
        assert not cmd.is_expired

    def test_default_status(self):
        cmd = Command(id=1, command="test")
        assert cmd.status == "pending"


# ─── claim_next ──────────────────────────────────────────────────────

class TestClaimNext:
    def test_returns_command(self):
        cmd = Command(id=1, command="extract_all", params={"foo": "bar"})
        q, _, _ = _make_queue(claim_return=cmd)
        claimed = q.claim_next()
        assert claimed.id == 1
        assert claimed.command == "extract_all"

    def test_returns_none(self):
        q, _, _ = _make_queue()
        assert q.claim_next() is None


# ─── mark_done / mark_error ──────────────────────────────────────────

class TestMarkStatus:
    def test_mark_done(self):
        q, updates, _ = _make_queue()
        result = q.mark_done(42, {"message": "ok"})
        assert result.status == "done"
        assert result.command_id == 42
        assert updates == [(42, "done", {"message": "ok"})]

    def test_mark_error(self):
        q, updates, _ = _make_queue()
        result = q.mark_error(42, "boom")
        assert result.status == "error"
        assert updates == [(42, "error", {"error": "boom"})]


# ─── requeue ─────────────────────────────────────────────────────────

class TestRequeue:
    def test_requeue(self):
        q, _, requeues = _make_queue()
        q.requeue(99)
        assert requeues == [99]


# ─── cancel_pending ──────────────────────────────────────────────────

class TestCancelPending:
    def test_cancel(self):
        q, _, _ = _make_queue(cancel_count=5)
        assert q.cancel_pending() == 5

    def test_cancel_with_exclude(self):
        q, _, _ = _make_queue(cancel_count=3)
        assert q.cancel_pending(exclude_commands=["print_label"]) == 3


# ─── expire_old ──────────────────────────────────────────────────────

class TestExpireOld:
    def test_expire(self):
        q, _, _ = _make_queue(expire_count=2)
        assert q.expire_old() == 2

    def test_expire_with_filter(self):
        q, _, _ = _make_queue(expire_count=1)
        assert q.expire_old(command_filter=["print_label"]) == 1


# ─── count_pending ───────────────────────────────────────────────────

class TestCountPending:
    def test_count(self):
        q, _, _ = _make_queue(pending_count=7)
        assert q.count_pending() == 7

    def test_count_with_filter(self):
        q, _, _ = _make_queue(pending_count=3)
        assert q.count_pending(command_filter=["print_label"]) == 3


# ─── CommandResult ───────────────────────────────────────────────────

def test_command_result_defaults():
    r = CommandResult(command_id=1, status="done")
    assert r.result == {}

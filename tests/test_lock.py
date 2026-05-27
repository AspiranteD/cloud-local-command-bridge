"""Tests for distributed lock with heartbeat and failover."""
import time
import pytest
from src.lock.distributed_lock import (
    DistributedLock, LockCallbacks, LockState,
    HEARTBEAT_INTERVAL, LOCK_TIMEOUT, LOCK_RETRY_INTERVAL,
    SAME_HOST_RETRY_INTERVAL,
    get_instance_id, get_hostname,
)


def _make_callbacks(
    state=None,
    acquire_result=True,
    heartbeat_result=True,
    released=None,
):
    if released is None:
        released = []
    if state is None:
        state = LockState()
    return LockCallbacks(
        read_lock=lambda: state,
        try_acquire=lambda h, i: acquire_result,
        send_heartbeat=lambda i: heartbeat_result,
        release=lambda i: released.append(i),
    )


# ─── LockState ────────────────────────────────────────────────────────

class TestLockState:
    def test_not_held(self):
        s = LockState()
        assert not s.is_held
        assert s.is_expired

    def test_held(self):
        s = LockState(locked_by="pc1", heartbeat_at=time.time())
        assert s.is_held
        assert not s.is_expired

    def test_expired(self):
        s = LockState(locked_by="pc1", heartbeat_at=time.time() - LOCK_TIMEOUT - 1)
        assert s.is_held
        assert s.is_expired

    def test_same_host(self):
        s = LockState(locked_by="pc1")
        assert s.is_same_host("pc1")
        assert not s.is_same_host("pc2")

    def test_same_host_stale(self):
        s = LockState(
            locked_by="pc1",
            heartbeat_at=time.time() - SAME_HOST_RETRY_INTERVAL - 1,
        )
        assert s.is_same_host_stale("pc1")
        assert not s.is_same_host_stale("pc2")

    def test_same_host_fresh(self):
        s = LockState(locked_by="pc1", heartbeat_at=time.time())
        assert not s.is_same_host_stale("pc1")

    def test_no_heartbeat_is_stale(self):
        s = LockState(locked_by="pc1", heartbeat_at=None)
        assert s.is_same_host_stale("pc1")


# ─── DistributedLock.try_acquire ──────────────────────────────────────

class TestLockAcquire:
    def test_acquire_free(self):
        cb = _make_callbacks(state=LockState())
        lock = DistributedLock(cb)
        assert lock.try_acquire()
        assert lock.is_active

    def test_acquire_expired(self):
        state = LockState(
            locked_by="other",
            heartbeat_at=time.time() - LOCK_TIMEOUT - 1,
        )
        cb = _make_callbacks(state=state)
        lock = DistributedLock(cb)
        assert lock.try_acquire()

    def test_cannot_acquire_active(self):
        state = LockState(locked_by="other", heartbeat_at=time.time())
        cb = _make_callbacks(state=state, acquire_result=False)
        lock = DistributedLock(cb)
        assert not lock.try_acquire()
        assert not lock.is_active

    def test_acquire_same_host_stale(self):
        lock = DistributedLock(_make_callbacks())
        state = LockState(
            locked_by=lock.hostname,
            heartbeat_at=time.time() - SAME_HOST_RETRY_INTERVAL - 1,
        )
        lock._cb.read_lock = lambda: state
        assert lock.try_acquire()

    def test_cannot_acquire_same_host_fresh(self):
        lock = DistributedLock(_make_callbacks(acquire_result=False))
        state = LockState(
            locked_by=lock.hostname,
            heartbeat_at=time.time(),
        )
        lock._cb.read_lock = lambda: state
        assert not lock.try_acquire()


# ─── DistributedLock.heartbeat ────────────────────────────────────────

class TestLockHeartbeat:
    def test_heartbeat_not_active(self):
        cb = _make_callbacks()
        lock = DistributedLock(cb)
        assert not lock.send_heartbeat()

    def test_heartbeat_too_soon(self):
        cb = _make_callbacks()
        lock = DistributedLock(cb)
        lock.is_active = True
        lock._last_heartbeat = time.time()
        assert lock.send_heartbeat()

    def test_heartbeat_sends(self):
        sent = []
        cb = _make_callbacks()
        cb.send_heartbeat = lambda i: (sent.append(i), True)[1]
        lock = DistributedLock(cb)
        lock.is_active = True
        lock._last_heartbeat = 0
        assert lock.send_heartbeat()
        assert len(sent) == 1

    def test_heartbeat_lost(self):
        cb = _make_callbacks(heartbeat_result=False)
        lock = DistributedLock(cb)
        lock.is_active = True
        lock._last_heartbeat = 0
        assert not lock.send_heartbeat()
        assert not lock.is_active


# ─── DistributedLock.release ──────────────────────────────────────────

class TestLockRelease:
    def test_release_active(self):
        released = []
        cb = _make_callbacks(released=released)
        lock = DistributedLock(cb)
        lock.is_active = True
        lock.release()
        assert not lock.is_active
        assert len(released) == 1

    def test_release_inactive(self):
        released = []
        cb = _make_callbacks(released=released)
        lock = DistributedLock(cb)
        lock.release()
        assert len(released) == 0


# ─── DistributedLock.retry_interval ──────────────────────────────────

class TestRetryInterval:
    def test_same_host_shorter(self):
        lock = DistributedLock(_make_callbacks())
        state = LockState(locked_by=lock.hostname)
        lock._cb.read_lock = lambda: state
        assert lock.compute_retry_interval() == SAME_HOST_RETRY_INTERVAL

    def test_other_host_longer(self):
        state = LockState(locked_by="other_pc")
        lock = DistributedLock(_make_callbacks(state=state))
        assert lock.compute_retry_interval() == LOCK_RETRY_INTERVAL


# ─── Utility ─────────────────────────────────────────────────────────

def test_instance_id_format():
    iid = get_instance_id()
    assert ":" in iid

def test_hostname():
    assert len(get_hostname()) > 0

def test_holder_info_free():
    lock = DistributedLock(_make_callbacks(state=LockState()))
    assert "free" in lock.get_holder_info()

def test_holder_info_held():
    state = LockState(locked_by="pc1", heartbeat_at=123.0)
    lock = DistributedLock(_make_callbacks(state=state))
    info = lock.get_holder_info()
    assert "pc1" in info

"""Tests for DistributedLock."""

import time
import pytest

from src.locking.distributed_lock import DistributedLock, LockStore


@pytest.fixture
def store():
    return LockStore()


class TestDistributedLock:
    def test_acquire_and_release(self, store):
        lock = DistributedLock(store, key="cmd-1", owner="worker-A")
        assert lock.acquire() is True
        assert lock.is_acquired is True
        assert lock.release() is True
        assert lock.is_acquired is False

    def test_cannot_acquire_held_lock(self, store):
        lock_a = DistributedLock(store, key="cmd-1", owner="worker-A")
        lock_b = DistributedLock(store, key="cmd-1", owner="worker-B")
        lock_a.acquire()
        assert lock_b.acquire() is False

    def test_different_keys_independent(self, store):
        lock_a = DistributedLock(store, key="cmd-1", owner="worker-A")
        lock_b = DistributedLock(store, key="cmd-2", owner="worker-B")
        assert lock_a.acquire() is True
        assert lock_b.acquire() is True

    def test_lock_expiry(self, store):
        lock_a = DistributedLock(store, key="cmd-1", owner="worker-A", ttl=0.1)
        lock_a.acquire()
        time.sleep(0.15)
        lock_b = DistributedLock(store, key="cmd-1", owner="worker-B")
        assert lock_b.acquire() is True

    def test_release_by_wrong_owner_fails(self, store):
        lock_a = DistributedLock(store, key="cmd-1", owner="worker-A")
        lock_a.acquire()
        lock_b = DistributedLock(store, key="cmd-1", owner="worker-B")
        lock_b._acquired = True
        assert lock_b.release() is False

    def test_context_manager_success(self, store):
        with DistributedLock(store, key="cmd-1", owner="worker-A") as lock:
            assert lock.is_acquired is True
        assert not store.is_locked("cmd-1")

    def test_context_manager_already_held_raises(self, store):
        lock_a = DistributedLock(store, key="cmd-1", owner="worker-A")
        lock_a.acquire()
        with pytest.raises(RuntimeError, match="Failed to acquire"):
            with DistributedLock(store, key="cmd-1", owner="worker-B"):
                pass

    def test_owner_tracking(self, store):
        lock = DistributedLock(store, key="cmd-1", owner="worker-A")
        lock.acquire()
        assert store.get_owner("cmd-1") == "worker-A"

    def test_acquire_with_timeout_retries(self, store):
        import threading

        lock_a = DistributedLock(store, key="cmd-1", owner="worker-A", ttl=0.2)
        lock_a.acquire()

        def release_later():
            time.sleep(0.1)
            lock_a.release()

        threading.Thread(target=release_later).start()
        lock_b = DistributedLock(store, key="cmd-1", owner="worker-B")
        assert lock_b.acquire(timeout=0.5) is True

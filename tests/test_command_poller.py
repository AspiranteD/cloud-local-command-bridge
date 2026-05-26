"""Tests for CommandPoller."""

import pytest
import threading
import time

from src.poller.command_poller import (
    CommandPoller,
    CommandQueue,
    Command,
    CommandStatus,
)


@pytest.fixture
def queue():
    return CommandQueue()


@pytest.fixture
def poller(queue):
    return CommandPoller(queue=queue, poll_interval=0.1)


class TestCommandQueue:
    def test_push_and_get_pending(self, queue):
        cmd = Command(id="cmd-1", name="TEST")
        queue.push(cmd)
        result = queue.get_oldest_pending()
        assert result is not None
        assert result.id == "cmd-1"

    def test_empty_queue_returns_none(self, queue):
        assert queue.get_oldest_pending() is None

    def test_oldest_pending_ordering(self, queue):
        cmd1 = Command(id="cmd-1", name="FIRST")
        time.sleep(0.01)
        cmd2 = Command(id="cmd-2", name="SECOND")
        queue.push(cmd2)
        queue.push(cmd1)
        result = queue.get_oldest_pending()
        assert result.id == "cmd-1"


class TestCommandPoller:
    def test_poll_empty_queue(self, poller):
        assert poller.poll() is None

    def test_poll_returns_pending_command(self, poller, queue):
        cmd = Command(id="cmd-1", name="TEST")
        queue.push(cmd)
        result = poller.poll()
        assert result.id == "cmd-1"

    def test_acknowledge_marks_in_progress(self, poller, queue):
        cmd = Command(id="cmd-1", name="TEST")
        queue.push(cmd)
        poller.acknowledge("cmd-1")
        updated = queue.get("cmd-1")
        assert updated.status == CommandStatus.IN_PROGRESS
        assert updated.started_at is not None

    def test_acknowledge_nonexistent_raises(self, poller):
        with pytest.raises(ValueError):
            poller.acknowledge("nonexistent")

    def test_complete_marks_completed(self, poller, queue):
        cmd = Command(id="cmd-1", name="TEST")
        queue.push(cmd)
        poller.acknowledge("cmd-1")
        poller.complete("cmd-1", result={"data": 42})
        updated = queue.get("cmd-1")
        assert updated.status == CommandStatus.COMPLETED
        assert updated.result == {"data": 42}
        assert updated.completed_at is not None

    def test_fail_marks_failed(self, poller, queue):
        cmd = Command(id="cmd-1", name="TEST")
        queue.push(cmd)
        poller.acknowledge("cmd-1")
        poller.fail("cmd-1", error="Something went wrong")
        updated = queue.get("cmd-1")
        assert updated.status == CommandStatus.FAILED
        assert updated.error == "Something went wrong"

    def test_commands_processed_counter(self, queue):
        executor = lambda name, params: "ok"
        poller = CommandPoller(queue=queue, executor=executor, poll_interval=0.01)
        cmd = Command(id="cmd-1", name="TEST")
        queue.push(cmd)
        poller._process_one()
        assert poller.commands_processed == 1

    def test_run_forever_stops_gracefully(self, queue):
        executor = lambda name, params: "ok"
        poller = CommandPoller(queue=queue, executor=executor, poll_interval=0.05)

        def stop_after_delay():
            time.sleep(0.15)
            poller.stop()

        stopper = threading.Thread(target=stop_after_delay)
        stopper.start()
        poller.run_forever()
        stopper.join()
        assert not poller.is_running

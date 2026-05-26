"""
Demo: Cloud-Local Command Bridge

Shows the full lifecycle:
1. Register commands
2. Enqueue a command (simulating cloud side)
3. Poller picks it up, executes, and reports result
"""

import time
from src.poller.command_poller import CommandPoller, CommandQueue, Command
from src.executor.command_executor import CommandExecutor
from src.executor.command_registry import CommandRegistry
from src.locking.distributed_lock import DistributedLock, LockStore
from src.heartbeat.heartbeat import HeartbeatReporter, HeartbeatStore


def main():
    # --- Setup ---
    registry = CommandRegistry(include_builtins=True)

    # Register a custom command
    registry.register(
        "SCRAPE_PRICES",
        handler=lambda url="https://example.com": f"Scraped 42 items from {url}",
        timeout=30.0,
        description="Scrape product prices from a URL",
    )

    executor = CommandExecutor(registry=registry)
    lock_store = LockStore()
    heartbeat_store = HeartbeatStore()

    # --- Wire up the poller with the executor ---
    queue = CommandQueue()

    def execute_with_lock(command_name: str, params: dict):
        lock = DistributedLock(lock_store, key=f"cmd-lock-{command_name}", ttl=60)
        with lock:
            result = executor.execute(command_name, params)
            if not result.success:
                raise RuntimeError(result.error)
            return result.output

    poller = CommandPoller(queue=queue, executor=execute_with_lock, poll_interval=1.0)

    # --- Start heartbeat ---
    heartbeat = HeartbeatReporter(
        store=heartbeat_store,
        interval=5.0,
        commands_counter=lambda: poller.commands_processed,
    )
    heartbeat.start()

    # --- Simulate cloud side enqueueing commands ---
    print("=== Cloud-Local Command Bridge Demo ===\n")
    print("Simulating cloud dashboard enqueueing commands...\n")

    queue.push(Command(id="cmd-001", name="PING", params={}))
    queue.push(Command(id="cmd-002", name="STATUS", params={}))
    queue.push(Command(id="cmd-003", name="SCRAPE_PRICES", params={"url": "https://store.example.com"}))

    # --- Process commands (instead of run_forever, process manually for demo) ---
    for _ in range(3):
        cmd = poller.poll()
        if cmd:
            print(f"Processing: {cmd.name} (id={cmd.id})")
            poller.acknowledge(cmd.id)
            try:
                result = execute_with_lock(cmd.name, cmd.params)
                poller.complete(cmd.id, result)
                print(f"  ✓ Result: {result}\n")
            except Exception as e:
                poller.fail(cmd.id, str(e))
                print(f"  ✗ Error: {e}\n")

    # --- Report final heartbeat ---
    beat = heartbeat.report_now()
    print(f"--- Heartbeat ---")
    print(f"  Host: {beat.hostname}")
    print(f"  Commands processed: {beat.commands_processed}")
    print(f"  Uptime: {beat.uptime_seconds}s")

    heartbeat.stop()
    print("\nBridge demo complete.")


if __name__ == "__main__":
    main()

# Cloud-Local Command Bridge
> **Portfolio context:** Extracted from founder-led production systems — multi-marketplace inventory, orders, and warehouse execution. **[Full portfolio](https://github.com/AspiranteD/AspiranteD)** · [aspiranted.github.io](https://aspiranted.github.io)

Production bridge connecting a cloud-hosted low-code platform (Retool) to local backend instances via a shared PostgreSQL queue. Enables remote command execution (extractions, printer control, enrichment) across distributed machines with automatic failover.

## Architecture

```
src/
+-- lock/
¦   +-- distributed_lock.py   # Exclusive lock with heartbeat + failover
+-- queue/
¦   +-- command_queue.py       # Claim-execute-update command pattern
¦   +-- dispatcher.py         # Command routing to handlers
+-- printer/
    +-- printer_discovery.py   # TTL-cached printer detection + heartbeat
```

## Key Technical Features

### Distributed Lock (`src/lock/distributed_lock.py`)

Ensures exactly one backend instance processes commands at a time:

- **Heartbeat-based liveness**: active instance sends heartbeat every 10s
- **Automatic failover**: if heartbeat stops for 60s, another instance can take over
- **Same-host fast recovery**: if the same hostname tries to acquire (process restart), shorter 10s timeout
- **Graceful release**: on shutdown, explicitly releases lock and cancels pending commands
- **Lock state inspection**: can query current holder and heartbeat age

### Command Queue (`src/queue/command_queue.py`)

PostgreSQL-backed command queue with transactional claim semantics:

- **Claim-execute-update**: `pending` -> `processing` -> `done`/`error`
- **SKIP LOCKED**: concurrent workers can poll without double-processing
- **TTL expiration**: commands older than configurable TTL auto-expire
- **Requeue on transient failure**: if a command fails due to missing hardware (printer), it returns to `pending` for another worker
- **Graceful shutdown**: cancels pending commands (excluding transferable ones like print/enrich)
- **Filtered polling**: print commands use separate polling loop with faster interval

### Command Dispatcher (`src/queue/dispatcher.py`)

Extensible command routing:

- **Handler registration**: `register("command_name", handler_fn)`
- **Error isolation**: handler exceptions are caught and returned as structured errors
- **Result normalization**: non-dict returns wrapped automatically
- **Real-world commands**: start/stop scheduler, run individual extraction jobs, set intervals, update/validate cookies, print labels, enrich items

### Printer Discovery (`src/printer/printer_discovery.py`)

Handles printer detection across distributed machines:

- **TTL-based caching**: avoids OS-level detection (USB/PowerShell) every poll cycle. Successful detections cached for 60s
- **Negative cache bypass**: failed detections are never cached (retry immediately)
- **Printer heartbeat**: registers PC availability in DB so cloud UI can list printers
- **Cache invalidation**: explicit `invalidate_cache()` on printer errors forces re-detection
- **Multi-PC support**: any PC with a printer can process print commands via target_pc routing

### Concurrency Model

- **Lock holder**: runs command poll (5s), heartbeat (10s), cookie validation (30min)
- **All instances**: run print poll (2s) independently (no lock needed)
- **Lock loss detection**: heartbeat loop detects if another instance took over, transitions to standby
- **Standby re-acquisition**: standby instances retry lock acquisition every 30s

## Testing

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

**69 tests** covering:
- Lock state (held, expired, same-host stale, fresh)
- Lock acquisition (free, expired holder, same-host restart, active holder)
- Heartbeat (throttling, loss detection, status update)
- Command queue (claim, done, error, requeue, cancel, expire, count)
- Dispatcher (registration, unknown commands, exceptions, real-world patterns)
- Printer discovery (caching, expiry, invalidation, heartbeat throttling)

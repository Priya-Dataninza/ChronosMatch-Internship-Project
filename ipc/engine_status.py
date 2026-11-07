import os
import sqlite3
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "ledger.db"
STATUS_STALE_AFTER_NS = 5_000_000_000


def publish_engine_status(status_queue, status, **metrics):
    status_queue.put({
        "kind": "engine_status",
        "status": status,
        "pid": os.getpid(),
        "updated_at_ns": time.monotonic_ns(),
        "engine_type": metrics.get("engine_type"),
        "orders_processed": metrics.get("orders_processed", 0),
        "trades_executed": metrics.get("trades_executed", 0),
        "last_latency_ns": metrics.get("last_latency_ns"),
        "average_latency_ns": metrics.get("average_latency_ns"),
        "max_latency_ns": metrics.get("max_latency_ns"),
    })


def read_engine_status(db_path=DB_PATH, now_ns=None):
    stopped = {
        "status": "stopped",
        "pid": None,
        "orders_processed": 0,
        "trades_executed": 0,
        "last_latency_ns": None,
        "average_latency_ns": None,
        "max_latency_ns": None,
    }

    if not Path(db_path).exists():
        return stopped

    connection = sqlite3.connect(db_path, timeout=1)
    connection.row_factory = sqlite3.Row
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='engine_status'"
        ).fetchone()
        if table_exists is None:
            return stopped

        row = connection.execute(
            "SELECT status, pid, updated_at_ns, engine_type, "
            "orders_processed, trades_executed, last_latency_ns, "
            "average_latency_ns, max_latency_ns "
            "FROM engine_status WHERE id=1"
        ).fetchone()
        if row is None:
            return stopped

        payload = dict(row)
        current_time_ns = time.monotonic_ns() if now_ns is None else now_ns
        if (
            payload["status"] == "running"
            and current_time_ns - payload["updated_at_ns"]
            > STATUS_STALE_AFTER_NS
        ):
            payload["status"] = "stale"
        return payload
    finally:
        connection.close()

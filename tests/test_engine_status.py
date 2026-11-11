import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from ipc.engine_status import (
    STATUS_STALE_AFTER_NS,
    publish_engine_status,
    read_engine_status,
)
from ipc.trade_ledger import trade_writer


class StatusQueue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class TestEngineStatus(unittest.TestCase):
    def test_missing_status_reports_stopped_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ledger.db"

            status = read_engine_status(db_path)

        self.assertEqual(status["status"], "stopped")
        self.assertIsNone(status["average_latency_ns"])

    def test_status_heartbeat_and_latency_metrics_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ledger.db"
            queue = StatusQueue()
            publish_engine_status(
                queue,
                "running",
                engine_type="cython",
                orders_processed=12,
                trades_executed=3,
                last_latency_ns=900,
                average_latency_ns=1200,
                max_latency_ns=2400,
            )

            trade_writer(ItemsQueue([*queue.items, None]), db_path)
            status = read_engine_status(db_path)

        self.assertEqual(status["status"], "running")
        self.assertEqual(status["average_latency_ns"], 1200)
        self.assertEqual(status["orders_processed"], 12)

    def test_old_running_heartbeat_is_marked_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ledger.db"
            trade_writer(ItemsQueue([None]), db_path)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "INSERT INTO engine_status "
                    "(id, status, pid, updated_at_ns, engine_type, "
                    "orders_processed, trades_executed) "
                    "VALUES (1, 'running', 1, ?, 'cython', 0, 0)",
                    (time.monotonic_ns() - STATUS_STALE_AFTER_NS - 1,),
                )
                connection.commit()
            finally:
                connection.close()

            status = read_engine_status(db_path)

        self.assertEqual(status["status"], "stale")


class ItemsQueue:
    def __init__(self, items):
        self.items = iter(items)

    def get(self):
        return next(self.items)


if __name__ == "__main__":
    unittest.main()

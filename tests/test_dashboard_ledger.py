import sqlite3
import tempfile
import unittest
from pathlib import Path

from dashboard.latency_dashboard import (
    clears_multiple_levels,
    ledger_writer,
)
from ipc.trade_ledger import trade_writer


class BatchQueue:
    def __init__(self, batches):
        self.batches = iter(batches)

    def get(self):
        return next(self.batches)


class TestDashboardLedger(unittest.TestCase):
    def test_whale_requires_large_order_and_multiple_filled_levels(self):
        fills = [
            {"price": 10000},
            {"price": 10100},
        ]

        self.assertTrue(clears_multiple_levels(100, fills))
        self.assertFalse(clears_multiple_levels(50, fills))
        self.assertFalse(clears_multiple_levels(100, [fills[0]]))

    def test_writer_persists_execution_batches(self):
        trade = (101, 202, 10000, 3, 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ledger.db"
            queue = BatchQueue([[trade], [], None])

            ledger_writer(queue, str(db_path))

            connection = sqlite3.connect(db_path)
            try:
                rows = connection.execute(
                    "SELECT maker_order_id, taker_order_id, price, "
                    "quantity, side FROM executed_trades"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(rows, [trade])

    def test_engine_ledger_writer_uses_web_dashboard_schema(self):
        trade = {
            "maker_order_id": 301,
            "taker_order_id": 302,
            "price": 10250,
            "quantity": 6,
            "side": 2,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ledger.db"
            queue = BatchQueue([[trade], None])

            trade_writer(queue, db_path)

            connection = sqlite3.connect(db_path)
            try:
                rows = connection.execute(
                    "SELECT maker_order_id, taker_order_id, price, "
                    "quantity, side FROM executed_trades"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(rows, [(301, 302, 10250, 6, 2)])


if __name__ == "__main__":
    unittest.main()

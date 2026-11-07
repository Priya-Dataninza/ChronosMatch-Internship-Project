
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "ledger.db"


def trade_writer(queue, db_path=DB_PATH):
    """Persist execution batches on the supplied queue."""

    connection = sqlite3.connect(db_path)

    connection.execute("PRAGMA journal_mode=WAL")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS executed_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maker_order_id INTEGER NOT NULL,
            taker_order_id INTEGER NOT NULL,
            price INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            side INTEGER NOT NULL,
            executed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()

    print("[AUDIT] SQLite writer online.")

    try:
        while True:
            batch = queue.get()

            if batch is None:
                break

            if not batch:
                continue

            connection.executemany("""
                INSERT INTO executed_trades (
                    maker_order_id,
                    taker_order_id,
                    price,
                    quantity,
                    side
                )
                VALUES (?, ?, ?, ?, ?)
            """, [
                (
                    trade["maker_order_id"],
                    trade["taker_order_id"],
                    trade["price"],
                    trade["quantity"],
                    trade["side"]
                )
                for trade in batch
            ])

            connection.commit()

    finally:
        connection.close()
        print("[AUDIT] SQLite writer stopped.")

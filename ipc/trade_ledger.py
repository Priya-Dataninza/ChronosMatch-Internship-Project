
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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS engine_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            status TEXT NOT NULL,
            pid INTEGER,
            updated_at_ns INTEGER NOT NULL,
            engine_type TEXT,
            orders_processed INTEGER NOT NULL,
            trades_executed INTEGER NOT NULL,
            last_latency_ns INTEGER,
            average_latency_ns INTEGER,
            max_latency_ns INTEGER
        )
    """)

    connection.commit()

    print("[AUDIT] SQLite writer online.")

    try:
        while True:
            batch = queue.get()

            if batch is None:
                break

            if isinstance(batch, dict) and batch.get("kind") == "engine_status":
                connection.execute("""
                    INSERT OR REPLACE INTO engine_status (
                        id, status, pid, updated_at_ns, engine_type,
                        orders_processed, trades_executed, last_latency_ns,
                        average_latency_ns, max_latency_ns
                    )
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    batch["status"],
                    batch["pid"],
                    batch["updated_at_ns"],
                    batch["engine_type"],
                    batch["orders_processed"],
                    batch["trades_executed"],
                    batch["last_latency_ns"],
                    batch["average_latency_ns"],
                    batch["max_latency_ns"],
                ))
                connection.commit()
                continue

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

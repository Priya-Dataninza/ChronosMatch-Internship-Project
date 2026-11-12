
import os
from queue import Queue
from threading import Thread
import time
from time import perf_counter_ns

from ipc.shared_buffer import (
    init_ring_buffer,
    get_mmap_instance,
    buffer_lock,
    HEADER_FORMAT,
    HEADER_SIZE,
    ORDER_FORMAT,
    ORDER_SIZE,
    MAX_ORDERS,
)


import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STOP_FILE = os.environ.get("CHRONOS_STOP_FILE")
READY_FILE = os.environ.get("CHRONOS_READY_FILE")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    
from matching_engine_core.engine_loader import PyOrderBook
from ipc.engine_status import publish_engine_status
from ipc.trade_ledger import trade_writer

init_ring_buffer()
file_handle, shared_memory = get_mmap_instance()


def run_engine():
    print("[ENGINE] ChronosMatch core online.")

    order_book = PyOrderBook()
    audit_queue = Queue()
    audit_writer = Thread(
        target=trade_writer,
        args=(audit_queue,),
        name="chronosmatch-trade-ledger",
    )
    audit_writer.start()
    processed = 0
    executed_trades = 0
    total_latency_ns = 0
    last_latency_ns = None
    max_latency_ns = None
    last_status_update = 0.0
    engine_type = (
        "cython"
        if type(order_book).__module__ == "matching_engine_core.order_book"
        else "python-fallback"
    )
    log_each_order = False  # Set False for throughput testing.

    def publish_status(status):
        order_book_depth = order_book.get_market_depth()
        order_book_depth["summary"] = order_book.get_book_summary()
        publish_engine_status(
            audit_queue,
            status,
            engine_type=engine_type,
            orders_processed=processed,
            trades_executed=executed_trades,
            last_latency_ns=last_latency_ns,
            average_latency_ns=(
                total_latency_ns // processed if processed else None
            ),
            max_latency_ns=max_latency_ns,
            order_book=order_book_depth,
        )

    try:
        publish_status("running")
        if READY_FILE:
            ready_file = Path(READY_FILE)
            temporary_file = ready_file.with_name(ready_file.name + ".tmp")
            temporary_file.write_text(str(os.getpid()), encoding="ascii")
            os.replace(temporary_file, ready_file)

        while True:
            order = None

            with buffer_lock(file_handle):
                write_ptr, read_ptr = HEADER_FORMAT.unpack_from(
                    shared_memory, 0
                )

                if read_ptr < write_ptr:
                    slot_index = read_ptr % MAX_ORDERS
                    offset = HEADER_SIZE + slot_index * ORDER_SIZE

                    order = ORDER_FORMAT.unpack_from(
                        shared_memory, offset
                    )
                    HEADER_FORMAT.pack_into(
                        shared_memory, 0,
                        write_ptr, read_ptr + 1
                    )

            if order is None:
                now = time.monotonic()
                if STOP_FILE and Path(STOP_FILE).exists():
                    break
                if now - last_status_update >= 0.25:
                    publish_status("running")
                    last_status_update = now
                time.sleep(0.0001)
                continue

            order_id, price, qty, side = order

            if side not in (1, 2) or price == 0 or qty == 0:
                print(
                    f"[ENGINE] Invalid record at slot "
                    f"{read_ptr % MAX_ORDERS}; discarding it."
                )
                continue

            start_ns = perf_counter_ns()
            trades = order_book.process_incoming(
                order_id, price, qty, side
            )
            last_latency_ns = perf_counter_ns() - start_ns
            total_latency_ns += last_latency_ns
            max_latency_ns = (
                last_latency_ns
                if max_latency_ns is None
                else max(max_latency_ns, last_latency_ns)
            )
            executed_trades += len(trades)
            if trades:
                audit_queue.put(trades)
            processed += 1

            now = time.monotonic()
            if now - last_status_update >= 0.25:
                if STOP_FILE and Path(STOP_FILE).exists():
                    break
                publish_status("running")
                last_status_update = now

            if log_each_order:
                label = "BUY" if side == 1 else "SELL"
                print(
                    f"[ENGINE] ID={order_id} "
                    f"{label} price={price} qty={qty}"
                )

    except KeyboardInterrupt:
        print("\n[ENGINE] Shutting down.")

    finally:
        print(f"[ENGINE] Orders processed: {processed}")
        print(f"[ENGINE] Metrics: {order_book.metrics}")
        try:
            publish_status("stopped")
        finally:
            audit_queue.put(None)
            audit_writer.join()

    return order_book


if __name__ == "__main__":
    try:
        order_book = run_engine()
        print("\n[MARKET ANALYSIS]")

        market = order_book.get_market_imbalance()

        print(f"Bid Quantity: {market['bid_quantity']}")
        print(f"Ask Quantity: {market['ask_quantity']}")
        print(f"Imbalance: {market['imbalance']:.4f}")
        print(f"Market Pressure: {market['pressure']}")
    finally:
        shared_memory.close()
        file_handle.close()


from queue import Queue
from threading import Thread
import time

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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    
from matching_engine_core.engine_loader import PyOrderBook
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
    log_each_order = False  # Set False for throughput testing.

    try:
        while True:
            if processed >= 1_000_000:
                break

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
                time.sleep(0.0001)
                continue

            order_id, price, qty, side = order

            if side not in (1, 2) or price == 0 or qty == 0:
                print(
                    f"[ENGINE] Invalid record at slot "
                    f"{read_ptr % MAX_ORDERS}; discarding it."
                )
                continue

            trades = order_book.process_incoming(
                order_id, price, qty, side
            )
            if trades:
                audit_queue.put(trades)
            processed += 1

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

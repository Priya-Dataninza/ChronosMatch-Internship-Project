
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
    
from matching_engine_core.order_book_fallback import PyOrderBook

init_ring_buffer()
file_handle, shared_memory = get_mmap_instance()


def run_engine():
    print("[ENGINE] ChronosMatch core online.")

    order_book = PyOrderBook()
    processed = 0
    log_each_order = True  # Set False for throughput testing.

    try:
        while True:
            with buffer_lock(file_handle):
                write_ptr, read_ptr = HEADER_FORMAT.unpack_from(
                    shared_memory, 0
                )

                if read_ptr >= write_ptr:
                    order = None
                else:
                    slot_index = read_ptr % MAX_ORDERS
                    offset = HEADER_SIZE + slot_index * ORDER_SIZE

                    order = ORDER_FORMAT.unpack_from(
                        shared_memory, offset
                    )

                    order_id, price, qty, side = order

                    if side not in (1, 2) or price == 0 or qty == 0:
                        print(
                            f"[ENGINE] Invalid record at slot {slot_index}; "
                            "discarding it."
                        )
                    else:
                        # Process before freeing the slot.
                        order_book.process_incoming(
                            order_id, price, qty, side
                        )
                        processed += 1

                        if log_each_order:
                            label = "BUY" if side == 1 else "SELL"
                            print(
                                f"[ENGINE] ID={order_id} "
                                f"{label} price={price} qty={qty}"
                            )

                    # Consume this logical position exactly once
                    # under the shared lock.
                    HEADER_FORMAT.pack_into(
                        shared_memory, 0,
                        write_ptr, read_ptr + 1
                    )

            if order is None:
                time.sleep(0.0001)

    except KeyboardInterrupt:
        print("\n[ENGINE] Shutting down.")

    finally:
        print(f"[ENGINE] Orders processed: {processed}")
        print(f"[ENGINE] Metrics: {order_book.metrics}")


if __name__ == "__main__":
    try:
        run_engine()
    finally:
        shared_memory.close()
        file_handle.close()

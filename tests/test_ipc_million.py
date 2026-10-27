import multiprocessing as mp
import time

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TOTAL_ORDERS = 1_000_000
PRICE = 10_000
QUANTITY = 1


def producer_worker(total_orders):
    """Write orders into the shared mmap ring buffer."""
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

    init_ring_buffer()
    file_handle, mem = get_mmap_instance()

    submitted = 0

    try:
        while submitted < total_orders:
            wrote_order = False

            with buffer_lock(file_handle):
                write_ptr, read_ptr = HEADER_FORMAT.unpack_from(
                    mem, 0
                )

                if write_ptr - read_ptr < MAX_ORDERS:
                    order_id = submitted + 1

                    # Alternate SELL and BUY orders.
                    side = 2 if order_id % 2 == 1 else 1

                    slot = write_ptr % MAX_ORDERS
                    offset = HEADER_SIZE + slot * ORDER_SIZE

                    ORDER_FORMAT.pack_into(
                        mem,
                        offset,
                        order_id,
                        PRICE,
                        QUANTITY,
                        side,
                    )

                    HEADER_FORMAT.pack_into(
                        mem, 0, write_ptr + 1, read_ptr
                    )

                    submitted += 1
                    wrote_order = True

            if not wrote_order:
                time.sleep(0.00001)

    finally:
        mem.close()
        file_handle.close()

    print(f"[PRODUCER] Submitted: {submitted}")


def consumer_worker(total_orders, result_queue):
    """Consume orders from mmap and process them through Cython."""
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

    from matching_engine_core.order_book_fallback import PyOrderBook

    init_ring_buffer()
    file_handle, mem = get_mmap_instance()

    book = PyOrderBook()
    processed = 0
    invalid = 0

    try:
        while processed + invalid < total_orders:
            got_order = False

            with buffer_lock(file_handle):
                write_ptr, read_ptr = HEADER_FORMAT.unpack_from(
                    mem, 0
                )

                if read_ptr < write_ptr:
                    slot = read_ptr % MAX_ORDERS
                    offset = HEADER_SIZE + slot * ORDER_SIZE

                    order_id, price, quantity, side = (
                        ORDER_FORMAT.unpack_from(mem, offset)
                    )

                    if (
                        price > 0
                        and quantity > 0
                        and side in (1, 2)
                    ):
                        book.process_incoming(
                            order_id, price, quantity, side
                        )
                        processed += 1
                    else:
                        invalid += 1

                    HEADER_FORMAT.pack_into(
                        mem, 0, write_ptr, read_ptr + 1
                    )

                    got_order = True

            if not got_order:
                time.sleep(0.00001)

        result_queue.put({
            "processed": processed,
            "invalid": invalid,
            "metrics": book.metrics,
        })

    finally:
        mem.close()
        file_handle.close()


def main():
    from ipc.shared_buffer import reset_ring_buffer

    # Ensure the buffer starts with empty pointers.
    reset_ring_buffer()

    result_queue = mp.Queue()

    consumer = mp.Process(
        target=consumer_worker,
        args=(TOTAL_ORDERS, result_queue),
    )

    producer = mp.Process(
        target=producer_worker,
        args=(TOTAL_ORDERS,),
    )

    print("Starting million-order IPC benchmark...")

    start = time.perf_counter()

    consumer.start()
    producer.start()

    producer.join(timeout=600)

    if producer.is_alive():
        producer.terminate()
        producer.join()
        consumer.terminate()
        consumer.join()
        raise RuntimeError("Producer timed out.")

    if producer.exitcode != 0:
        consumer.terminate()
        consumer.join()
        raise RuntimeError(
            f"Producer failed with exit code {producer.exitcode}"
        )

    consumer.join(timeout=600)

    if consumer.is_alive():
        consumer.terminate()
        consumer.join()
        raise RuntimeError("Consumer timed out.")

    if consumer.exitcode != 0:
        raise RuntimeError(
            f"Consumer failed with exit code {consumer.exitcode}"
        )

    elapsed = time.perf_counter() - start

    try:
        result = result_queue.get(timeout=5)
    finally:
        result_queue.close()
        result_queue.join_thread()

    processed = result["processed"]
    invalid = result["invalid"]
    throughput = processed / elapsed if elapsed else 0

    print("\n========== IPC BENCHMARK ==========")
    print(f"Target orders:       {TOTAL_ORDERS:,}")
    print(f"Orders processed:    {processed:,}")
    print(f"Invalid records:     {invalid:,}")
    print(f"Engine metrics:      {result['metrics']}")
    print(f"Elapsed time:        {elapsed:.2f} seconds")
    print(f"Throughput:          {throughput:,.0f} orders/sec")

    passed = (
        processed == TOTAL_ORDERS
        and invalid == 0
        and result["metrics"]["total_processed"] == TOTAL_ORDERS
    )

    print(f"Result:              {'PASS' if passed else 'FAIL'}")
    print("===================================")

    if not passed:
        raise AssertionError(
            "The benchmark did not process exactly one million valid orders."
        )


if __name__ == "__main__":
    mp.freeze_support()
    main()

import time
from ipc import order_gateway

TOTAL_ORDERS = 1_000_000

accepted = 0
retries = 0

print("[GENERATOR] Starting...")

start = time.perf_counter()

try:
    while accepted < TOTAL_ORDERS:
        order_id = accepted + 1
        price = 10000
        quantity = 1

        # Alternate BUY and SELL.
        side = 1 if accepted % 2 == 0 else 2

        success = order_gateway.produce_order(
            order_id, price, quantity, side
        )

        if success:
            accepted += 1

            if accepted % 100_000 == 0:
                print(f"Sent {accepted:,} orders")

        else:
            retries += 1
            time.sleep(0.001)

    elapsed = time.perf_counter() - start

    print("\n[GENERATOR] Completed")
    print(f"Accepted: {accepted:,}")
    print(f"Retries: {retries:,}")
    print(f"Time: {elapsed:.2f} seconds")
    print(f"Throughput: {accepted / elapsed:,.0f} orders/sec")

finally:
    order_gateway.shared_memory.close()
    order_gateway.file_handle.close()

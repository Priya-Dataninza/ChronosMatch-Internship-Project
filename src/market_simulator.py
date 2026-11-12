
import argparse
import asyncio
import random
import time

from dataclasses import dataclass


PRICE_SCALE = 100
BATCH_SIZE = 256

SIDE_TO_CODE = {
    "BUY": 1,
    "SELL": 2,
}


@dataclass
class Order:
    """Represents a simulated market order."""

    order_id: int
    side: str
    price: float
    quantity: int
    timestamp_ns: int


def convert_order_for_gateway(
    order: Order,
) -> tuple[int, int, int, int]:
    """Convert an order into the integer format used by IPC."""

    try:
        side_code = SIDE_TO_CODE[order.side.upper()]
    except (AttributeError, KeyError) as error:
        raise ValueError("side must be BUY or SELL") from error

    price_cents = round(order.price * PRICE_SCALE)

    return (
        order.order_id,
        price_cents,
        order.quantity,
        side_code,
    )


def send_order_to_gateway(order: Order) -> bool:
    """Send a simulated order to the IPC gateway."""

    from ipc.order_gateway import produce_order

    order_id, price, quantity, side = (
        convert_order_for_gateway(order)
    )

    return produce_order(
        order_id,
        price,
        quantity,
        side,
    )


def send_orders_to_gateway(orders: list[Order]) -> bool:
    """Submit a batch atomically to the shared IPC queue."""

    from ipc.order_gateway import produce_orders

    return produce_orders([
        convert_order_for_gateway(order)
        for order in orders
    ])


async def generate_orders(
    total_orders: int = 10,
    delay: float = 0.5,
):
    """Generate simulated market orders asynchronously."""

    if total_orders < 0:
        raise ValueError("total_orders cannot be negative")

    if not 0 <= delay < float("inf"):
        raise ValueError("delay must be a finite non-negative number")

    for order_id in range(1, total_orders + 1):

        order = Order(
            order_id=order_id,
            side=random.choice(["BUY", "SELL"]),
            price=round(random.uniform(95.0, 105.0), 2),
            quantity=random.randint(1, 100),
            timestamp_ns=time.perf_counter_ns(),
        )

        yield order

        if delay:
            await asyncio.sleep(delay)


async def main():
    """Run the ChronosMatch market simulator."""

    parser = argparse.ArgumentParser(
        description="ChronosMatch market simulator"
    )

    parser.add_argument(
        "--orders",
        type=int,
        default=10,
        help="Number of orders to generate",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Delay between orders in seconds",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every generated order (reduces throughput)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100_000,
        help="Print progress after this many submitted orders",
    )

    args = parser.parse_args()

    if args.orders < 0:
        parser.error("--orders cannot be negative")

    if not 0 <= args.delay < float("inf"):
        parser.error("--delay must be finite and non-negative")
    if args.progress_every <= 0:
        parser.error("--progress-every must be positive")

    submitted = 0
    rejected = 0
    generated = 0
    batch = []
    batch_size = BATCH_SIZE if args.delay == 0 else 1
    start_time = time.perf_counter()
    next_progress = args.progress_every

    def report_progress():
        nonlocal next_progress
        if submitted >= next_progress or submitted == args.orders:
            elapsed = time.perf_counter() - start_time
            rate = submitted / elapsed if elapsed else 0
            print(
                f"[PROGRESS] {submitted:,}/{args.orders:,} orders "
                f"submitted | {rate:,.0f} orders/s | {elapsed:.1f}s"
            )
            next_progress = (
                submitted // args.progress_every + 1
            ) * args.progress_every

    try:
        async for order in generate_orders(
            args.orders,
            args.delay,
        ):
            generated += 1
            if args.verbose:
                print(
                    f"Order {order.order_id}: {order.side} | "
                    f"Price: {order.price:.2f} | "
                    f"Quantity: {order.quantity} | "
                    f"Timestamp: {order.timestamp_ns}"
                )

            batch.append(order)
            if len(batch) < batch_size:
                continue

            try:
                sent = send_orders_to_gateway(batch)
            except (ImportError, OSError) as error:
                print(f"[GATEWAY ERROR] {error}")
                rejected += len(batch)
                batch.clear()
                break

            if sent:
                submitted += len(batch)
                if args.verbose:
                    print(f"[GATEWAY] Submitted {len(batch)} orders.")
                batch.clear()
                report_progress()
            else:
                rejected += len(batch)
                batch.clear()
                print("[GATEWAY] Batch rejected; stopping the simulator.")
                break

        if batch:
            try:
                sent = send_orders_to_gateway(batch)
            except (ImportError, OSError) as error:
                print(f"[GATEWAY ERROR] {error}")
                rejected += len(batch)
            else:
                if sent:
                    submitted += len(batch)
                    if args.verbose:
                        print(f"[GATEWAY] Submitted {len(batch)} orders.")
                    report_progress()
                else:
                    rejected += len(batch)
                    print("[GATEWAY] Batch rejected.")

    finally:
        # Close gateway resources after simulation.
        import sys

        gateway = sys.modules.get("ipc.order_gateway")

        if gateway is not None:
            if hasattr(gateway, "shared_memory"):
                gateway.shared_memory.close()

            if hasattr(gateway, "file_handle"):
                gateway.file_handle.close()

    elapsed = time.perf_counter() - start_time
    rate = submitted / elapsed if elapsed else 0
    print(
        f"Orders generated: {generated}; "
        f"submitted: {submitted}; rejected: {rejected}; "
        f"elapsed: {elapsed:.2f}s; throughput: {rate:,.0f} orders/s"
    )


if __name__ == "__main__":
    asyncio.run(main())
